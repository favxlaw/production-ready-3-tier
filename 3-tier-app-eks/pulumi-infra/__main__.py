import pulumi
import pulumi_aws as aws
import pulumi_eks as eks
import pulumi_kubernetes as k8s
from pulumi_kubernetes.helm.v3 import Release, ReleaseArgs, RepositoryOptsArgs
from pulumi_aws import Provider

region = "us-east-1"


aws_provider = Provider("aws-provider", region=region)

current = aws.get_caller_identity()
account_id = current.account_id

common_tags = {
    "Project": "3-tier-demo",
    "Environment": "demo",
    "ManagedBy": "Pulumi",
    "Owner": "DevOps-Team"
}

# Create a custom VPC 
vpc = aws.ec2.Vpc("demo-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,  
    enable_dns_support=True,    
    tags={**common_tags, "Name": "demo-vpc"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create an Internet Gateway 
igw = aws.ec2.InternetGateway("demo-igw",
    vpc_id=vpc.id,
    tags={**common_tags, "Name": "demo-igw"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Get available availability zones in our region
azs = aws.get_availability_zones(state="available")

# Create PUBLIC subnets

public_subnet_1 = aws.ec2.Subnet("demo-public-subnet-1",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",  # 256 IP addresses
    availability_zone=azs.names[0],
    map_public_ip_on_launch=True,  # Instances here get public IPs automatically
    tags={**common_tags, "Name": "demo-public-subnet-1", "kubernetes.io/role/elb": "1"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

public_subnet_2 = aws.ec2.Subnet("demo-public-subnet-2",
    vpc_id=vpc.id,
    cidr_block="10.0.2.0/24",
    availability_zone=azs.names[1],
    map_public_ip_on_launch=True,
    tags={**common_tags, "Name": "demo-public-subnet-2", "kubernetes.io/role/elb": "1"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create PRIVATE subnets
private_subnet_1 = aws.ec2.Subnet("demo-private-subnet-1",
    vpc_id=vpc.id,
    cidr_block="10.0.3.0/24",
    availability_zone=azs.names[0],
    tags={**common_tags, "Name": "demo-private-subnet-1", "kubernetes.io/role/internal-elb": "1"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

private_subnet_2 = aws.ec2.Subnet("demo-private-subnet-2",
    vpc_id=vpc.id,
    cidr_block="10.0.4.0/24",
    availability_zone=azs.names[1],
    tags={**common_tags, "Name": "demo-private-subnet-2", "kubernetes.io/role/internal-elb": "1"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create NAT Gateway for private subnets
nat_eip = aws.ec2.Eip("demo-nat-eip",
    domain="vpc",
    tags={**common_tags, "Name": "demo-nat-eip"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

nat_gateway = aws.ec2.NatGateway("demo-nat-gateway",
    allocation_id=nat_eip.id,
    subnet_id=public_subnet_1.id,
    tags={**common_tags, "Name": "demo-nat-gateway"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create route table for PUBLIC subnets
public_route_table = aws.ec2.RouteTable("demo-public-rt",
    vpc_id=vpc.id,
    tags={**common_tags, "Name": "demo-public-rt"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Add route to internet gateway for public subnets
aws.ec2.Route("demo-public-route",
    route_table_id=public_route_table.id,
    destination_cidr_block="0.0.0.0/0",  # All traffic
    gateway_id=igw.id,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

aws.ec2.RouteTableAssociation("demo-public-rta-2",
    subnet_id=public_subnet_2.id,
    route_table_id=public_route_table.id,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)


# Create route table for PRIVATE subnets
private_route_table = aws.ec2.RouteTable("demo-private-rt",
    vpc_id=vpc.id,
    tags={**common_tags, "Name": "demo-private-rt"},
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Add route to NAT gateway for private subnets
aws.ec2.Route("demo-private-route",
    route_table_id=private_route_table.id,
    destination_cidr_block="0.0.0.0/0",
    nat_gateway_id=nat_gateway.id,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Associate private subnets with private route table
aws.ec2.RouteTableAssociation("demo-private-rta-1",
    subnet_id=private_subnet_1.id,
    route_table_id=private_route_table.id,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

aws.ec2.RouteTableAssociation("demo-private-rta-2",
    subnet_id=private_subnet_2.id,
    route_table_id=private_route_table.id,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create EKS cluster 
cluster = eks.Cluster("demo-cluster",
    vpc_id=vpc.id,
    subnet_ids=[public_subnet_1.id, public_subnet_2.id, private_subnet_1.id, private_subnet_2.id],
    instance_type="t3.medium",  
    desired_capacity=1,         # Starting with 1 node 
    min_size=1,
    max_size=3,                 # Can scale up to 3 if needed
    node_associate_public_ip_address=False,  
    tags=common_tags,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create IAM role for AWS Load Balancer Controller
alb_controller_role = aws.iam.Role("demo-alb-controller-role",
    assume_role_policy=pulumi.Output.all(
        cluster.core.oidc_provider.arn,
        cluster.core.oidc_provider.url
    ).apply(lambda args: f"""{{
        "Version": "2012-10-17",
        "Statement": [
            {{
                "Effect": "Allow",
                "Principal": {{
                    "Federated": "{args[0]}"
                }},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {{
                    "StringEquals": {{
                        "{args[1].replace('https://', '')}:sub": "system:serviceaccount:kube-system:aws-load-balancer-controller",
                        "{args[1].replace('https://', '')}:aud": "sts.amazonaws.com"
                    }}
                }}
            }}
        ]
    }}"""),
    tags=common_tags,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Attach the AWS Load Balancer Controller policy to our role
alb_controller_policy_attachment = aws.iam.RolePolicyAttachment("demo-alb-controller-policy",
    role=alb_controller_role.name,
    policy_arn="arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess",
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create additional policy for ALB Controller 
alb_controller_additional_policy = aws.iam.Policy("demo-alb-controller-additional-policy",
    description="Additional permissions for AWS Load Balancer Controller",
    policy="""{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DescribeAccountAttributes",
                    "ec2:DescribeAddresses",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeInternetGateways",
                    "ec2:DescribeVpcs",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeInstances",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:DescribeTags",
                    "ec2:GetCoipPoolUsage",
                    "ec2:DescribeCoipPools",
                    "elasticloadbalancing:DescribeLoadBalancers",
                    "elasticloadbalancing:DescribeLoadBalancerAttributes",
                    "elasticloadbalancing:DescribeListeners",
                    "elasticloadbalancing:DescribeListenerCertificates",
                    "elasticloadbalancing:DescribeSSLPolicies",
                    "elasticloadbalancing:DescribeRules",
                    "elasticloadbalancing:DescribeTargetGroups",
                    "elasticloadbalancing:DescribeTargetGroupAttributes",
                    "elasticloadbalancing:DescribeTargetHealth",
                    "elasticloadbalancing:DescribeTags"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:CreateTags"
                ],
                "Resource": "arn:aws:ec2:*:*:network-interface/*",
                "Condition": {
                    "StringEquals": {
                        "ec2:CreateAction": "CreateNetworkInterface"
                    }
                }
            }
        ]
    }""",
    tags=common_tags,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Attach the additional policy
alb_controller_additional_policy_attachment = aws.iam.RolePolicyAttachment("demo-alb-controller-additional-policy-attachment",
    role=alb_controller_role.name,
    policy_arn=alb_controller_additional_policy.arn,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)

# Create Kubernetes provider using our EKS cluster
k8s_provider = k8s.Provider("k8s-provider",
    kubeconfig=cluster.kubeconfig,
    opts=pulumi.ResourceOptions(depends_on=[cluster])
)

# Create service account for AWS Load Balancer Controller
alb_controller_service_account = k8s.core.v1.ServiceAccount("aws-load-balancer-controller",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="aws-load-balancer-controller",
        namespace="kube-system",
        annotations={
            "eks.amazonaws.com/role-arn": alb_controller_role.arn
        }
    ),
    opts=pulumi.ResourceOptions(provider=k8s_provider, depends_on=[cluster])
)

# Install AWS Load Balancer Controller using Helm
alb_controller_helm = Release("aws-load-balancer-controller",
    ReleaseArgs(
        name="aws-load-balancer-controller",
        chart="aws-load-balancer-controller",
        namespace="kube-system",
        repository_opts=RepositoryOptsArgs(
            repo="https://aws.github.io/eks-charts"
        ),
        values={
            "clusterName": cluster.name,
            "serviceAccount": {
                "create": False,  #created it above
                "name": "aws-load-balancer-controller"
            },
            "region": region,
            "vpcId": vpc.id,
        }
    ),
    opts=pulumi.ResourceOptions(provider=k8s_provider, depends_on=[alb_controller_service_account])
)

# Create a dedicated namespace for our application
app_namespace = k8s.core.v1.Namespace("app-namespace",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="app"
    ),
    opts=pulumi.ResourceOptions(provider=k8s_provider, depends_on=[cluster])
)

# CREATE KUBERNETES SECRETS AND CONFIGMAP
db_secret = k8s.core.v1.Secret("db-secret",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="db-secret",
        namespace="app"
    ),
    type="Opaque",
    string_data={
        "username": "demo_user",           # temporary, change in production
        "password": "demo_password_123",   # temporary, change in production
        "database": "demo_db"
    },
    opts=pulumi.ResourceOptions(provider=k8s_provider, depends_on=[app_namespace])
)

# Create a ConfigMap for non-sensitive configuration
db_config = k8s.core.v1.ConfigMap("db-config",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="db-config",
        namespace="app"
    ),
    data={
        "host": "demo-db-service.app.svc.cluster.local",  # Points to our ExternalName service
        "port": "5432",
        "database": "demo_db"
    },
    opts=pulumi.ResourceOptions(provider=k8s_provider, depends_on=[app_namespace])
)

# Create an ExternalName service

external_db_service = k8s.core.v1.Service("external-db-service",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="demo-db-service",
        namespace="app"
    ),
    spec=k8s.core.v1.ServiceSpecArgs(
        type="ExternalName",
        external_name="placeholder-rds-endpoint.us-east-1.rds.amazonaws.com",  # Update this with actual RDS endpoint
        ports=[k8s.core.v1.ServicePortArgs(
            port=5432,
            protocol="TCP"
        )]
    ),
    opts=pulumi.ResourceOptions(provider=k8s_provider, depends_on=[app_namespace])
)

pulumi.export("cluster_name", cluster.name)
pulumi.export("kubeconfig", cluster.kubeconfig)
pulumi.export("vpc_id", vpc.id)
pulumi.export("public_subnet_ids", [public_subnet_1.id, public_subnet_2.id])
pulumi.export("private_subnet_ids", [private_subnet_1.id, private_subnet_2.id])
pulumi.export("cluster_endpoint", cluster.core.endpoint)
pulumi.export("cluster_security_group_id", cluster.node_security_group_id)

import pulumi
import pulumi_aws as aws
import pulumi_eks as eks
import pulumi_kubernetes as k8s
from pulumi_kubernetes.helm.v3 import Release, ReleaseArgs, RepositoryOptsArgs

region = "us-east-1"

aws_provider = aws.provider("aws-provider", region=region)

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
    desired_capacity=1,         # Starting with 1 node for cost saving 
    min_size=1,
    max_size=3,                 # Can scale up to 3 if needed
    node_associate_public_ip_address=False,  # Nodes will be in private subnets
    tags=common_tags,
    opts=pulumi.ResourceOptions(provider=aws_provider)
)


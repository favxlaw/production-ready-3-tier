# EKS 3-Tier Application Deployment with Pulumi

This project demonstrates the deployment of a production-ready 3-tier application on AWS using Pulumi and Kubernetes.

The application consists of:
- **React Frontend** – provides the user interface.
- **Flask Backend API** – handles business logic.
- **PostgreSQL Database** – hosted on **Amazon RDS**, used for persistent storage.

## Architecture Overview

- **Amazon EKS**: Hosts the Kubernetes cluster for deploying and managing workloads.
- **Amazon RDS**: Provides a managed PostgreSQL database instance, provisioned in a private subnet.
- **Application Load Balancer (ALB)**: Automatically created by the AWS Load Balancer Controller to expose services via Ingress.
- **Route 53**: (Optional) Can be used to map the ALB to a custom domain.
- **Kubernetes Secrets & ConfigMaps**: Used to inject environment variables, credentials, and runtime configs into pods securely.
- **Kubernetes Job**: Executes database migrations before backend deployment to ensure the schema is up to date.
- **Helm Charts**: Used to simplify deployment of third-party services like the AWS Load Balancer Controller.

## Infrastructure as Code (IaC)

This deployment is fully managed using **Pulumi (Python)**. Key components provisioned include:

- VPC with private/public subnets
- EKS Cluster with small node group (`t3.small`)
- IAM Roles for service accounts (IRSA) to integrate Kubernetes with AWS services
- Security Groups for EKS and RDS communication
- PostgreSQL RDS instance in a private subnet
- Kubernetes namespace and deployment manifests
- Helm chart installations for ALB Controller and other utilities

## Workflow

This is a **demo-first project** optimized to keep AWS costs low:

- Run `pulumi up` when actively developing, testing, or demoing.
- Use a small EKS node group to minimize compute costs.
- When finished, run `pulumi destroy` to tear down resources.
- Recreate infrastructure only when needed.
- Use separate Pulumi stacks for dev/demo isolation.

## Future Enhancements

- Add autoscaling configuration (HPA, cluster autoscaler)
- Integrate CI/CD with GitHub Actions
- Set up observability stack (Prometheus, Grafana, CloudWatch Logs)

---

**Tools Used**:
- Pulumi (Python)
- AWS EKS, RDS, VPC, IAM, Route 53
- Docker
- Kubernetes + kubectl
- Helm
- GitHub Actions (CI/CD in future phase)

---

> ⚠️ This project is a controlled-cost deployment designed for learning, demos, and article documentation. Avoid leaving resources running when not in use.

> Note: The application code (frontend/backend) was adapted from an existing open-source project. All infrastructure setup and deployment logic is original work for learning/demo purposes.

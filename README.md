# Purchase Order System

A robust, cloud-native procurement and administrative workflow web platform designed to streamline purchase order and petty cash authorization pipelines, and dynamically compile formal quote sheets.

# Live Architecture Breakdown

The system is deployed on fully managed, 
enterprise-grade cloud infrastructure on AWS, utilizing a serverless container architecture for high availability and strict security isolation.

# Infrastructure & Core Tech Stack
* **Application Framework:** Django (Python 3.12)
* **Database Layer:** AWS RDS PostgreSQL (Engine v15+)
* **Containerization:** Docker & Docker Compose
* **Container Registry:** AWS ECR (Elastic Container Registry)
* **Orchestration Engine:** AWS ECS (Elastic Container Service) on **AWS Fargate** (Serverless)
* **CI/CD Pipeline Engine:** GitHub Actions

## 🛠️ Key DevOps & Cloud Engineering Achievements

### 1. Zero-Server Container Orchestration (AWS Fargate & ECR)
* Packaged the multi-layered Django application into an optimized **Docker production image**.
* Configured automated image shipping directly to **AWS Elastic Container Registry (ECR)**.
* Deployed the application to **AWS ECS utilizing serverless Fargate Tasks**, completely eliminating host VM maintenance overhead while leveraging isolated micro-allocations of virtual CPU and RAM.

### 2. Automated Continuous Integration / Continuous Deployment (CI/CD)
* Built an automated GitHub Actions pipeline (`build-test-and-deploy`) triggering on every mainline push.
* **Asset Compilation:** Docker compiles static production assets (`collectstatic`) seamlessly during the container build workspace layer using multi-layered compilation environments.
* **Secrets Management:** Implemented secure environment injection via `python-dotenv` to isolate high-risk cloud configurations from the public repository.

### 3. Enterprise Database Security & Custom Namespace Ownership
* Provisioned an **AWS RDS PostgreSQL** instance with strict Virtual Private Cloud (VPC) Security Groups, locking down public visibility and whitelisting strict TCP Port `5432` ingress access lines.
* **Database Resolution Engineering:** Conquered PostgreSQL 15+ strict default permission architectures by executing database-level role adjustments (`ALTER SCHEMA public OWNER TO ...`), allowing the containerized Django engine to cleanly execute migrations dynamically on the cloud layer.

---

## Local Environment Setup

To run this project locally for development or testing:

1. **Clone the repository:**
   bash
   git clone https://github.com/Sup3rAb3/purchase-order-system.git
   cd purchase-order-system

# ── VPC ──────────────────────────────────────────────────────────────────────
output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

# ── EKS ───────────────────────────────────────────────────────────────────────
output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "eks_cluster_certificate_authority" {
  description = "EKS cluster CA data (base64)"
  value       = aws_eks_cluster.main.certificate_authority[0].data
  sensitive   = true
}

output "eks_kubeconfig_command" {
  description = "AWS CLI command to update kubeconfig"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name} --profile sandbox"
}

# ── ECR ───────────────────────────────────────────────────────────────────────
output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app.repository_url
}

output "ecr_login_command" {
  description = "Docker login command for ECR"
  value       = "aws ecr get-login-password --region ${var.aws_region} --profile sandbox | docker login --username AWS --password-stdin ${aws_ecr_repository.app.repository_url}"
}

# ── RDS ───────────────────────────────────────────────────────────────────────
output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.postgres.endpoint
}

output "rds_db_name" {
  description = "RDS database name"
  value       = aws_db_instance.postgres.db_name
}

# ── ALB ───────────────────────────────────────────────────────────────────────
output "alb_dns_name" {
  description = "ALB public DNS name"
  value       = aws_lb.main.dns_name
}

output "alb_arn" {
  description = "ALB ARN"
  value       = aws_lb.main.arn
}

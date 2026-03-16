# ── RDS Subnet Group ──────────────────────────────────────────────────────────
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-rds-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name        = "${var.project_name}-rds-subnet-group"
    Environment = var.environment
  }
}

# ── RDS PostgreSQL Instance ───────────────────────────────────────────────────
resource "aws_db_instance" "postgres" {
  identifier        = "${var.project_name}-postgres"
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage
  storage_type      = "gp2"
  storage_encrypted = true

  db_name  = var.rds_db_name
  username = var.rds_username
  password = var.rds_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az            = false   # set true for production HA
  publicly_accessible = false
  skip_final_snapshot = true    # set false + add final_snapshot_identifier for production

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  monitoring_interval = 60
  monitoring_role_arn = aws_iam_role.rds_monitoring.arn

  tags = {
    Name        = "${var.project_name}-postgres"
    Environment = var.environment
  }
}

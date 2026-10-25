terraform {
  backend "s3" {
    bucket       = "4-tier-app-tfstate-707575990308-us-east-1"
    key          = "4-tier-app/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}

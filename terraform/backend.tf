terraform {
  backend "s3" {
    bucket       = "p5-eks-terraform-state"
    key          = "p5-eks/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
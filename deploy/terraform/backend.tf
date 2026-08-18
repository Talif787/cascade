# Remote state in a GCS bucket. The bucket must exist before init, and should
# have versioning enabled. Pass -backend-config at init time to avoid hardcoding
# the bucket, for example:
#   terraform init -backend-config="bucket=my-tf-state" -backend-config="prefix=cascade"
terraform {
  backend "gcs" {}
}

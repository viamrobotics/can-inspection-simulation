# Cloud Deployment Guide

## GitHub Container Registry Setup

### 1. GitHub Actions Workflow

The `.github/workflows/docker-build.yml` workflow automatically:
- Builds the Docker image on push to `main`/`master`
- Pushes to `ghcr.io/<your-username>/can-inspection-simulation`
- Tags with commit SHA and `latest`
- Uses GitHub Actions cache for faster builds

**To trigger**:
```bash
# Push to main branch
git add .github/workflows/docker-build.yml
git commit -m "Add Docker build workflow"
git push origin main
```

**Workflow will**:
1. Checkout code
2. Build Docker image
3. Push to ghcr.io (GitHub Container Registry)
4. Tag as `latest` and with commit SHA

### 2. Make Package Public

After first build, make the container image public:

1. Go to https://github.com/users/<your-username>/packages
2. Find `can-inspection-simulation`
3. Click "Package settings"
4. Scroll to "Danger Zone"
5. Click "Change visibility" → "Public"

## Running on GCP

### Option 1: GCP Compute Engine (Recommended)

**Deploy the container on GCP with access to web viewer on port 8081:**

```bash
# Pull the image
IMAGE="ghcr.io/<your-username>/can-inspection-simulation:latest"

# Create firewall rule for web viewer
gcloud compute firewall-rules create allow-can-inspection-web \
  --allow tcp:8081 \
  --target-tags=can-inspection \
  --description="Allow access to can inspection web viewer"

# Create instance and run container
gcloud compute instances create-with-container can-inspection-sim \
  --container-image=$IMAGE \
  --machine-type=n1-standard-2 \
  --tags=can-inspection \
  --zone=us-central1-a \
  --project=shared-playground-414521

# Get instance IP
INSTANCE_IP=$(gcloud compute instances describe can-inspection-sim \
  --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "Web viewer available at: http://$INSTANCE_IP:8081"
```

**With GPU (for better camera performance)**:

```bash
gcloud compute instances create can-inspection-sim \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --maintenance-policy=TERMINATE \
  --tags=can-inspection \
  --zone=us-central1-a \
  --metadata=gce-container-declaration="$(cat <<EOF
spec:
  containers:
  - name: can-inspection
    image: $IMAGE
    stdin: false
    tty: false
  restartPolicy: Always
EOF
)"
```

### Option 2: Cloud Run (Simpler, Serverless)

**Note**: Cloud Run has limitations for long-running simulations but good for testing.

```bash
# Deploy to Cloud Run
gcloud run deploy can-inspection-sim \
  --image=ghcr.io/<your-username>/can-inspection-simulation:latest \
  --platform=managed \
  --region=us-central1 \
  --allow-unauthenticated \
  --port=8081 \
  --memory=4Gi \
  --cpu=2 \
  --timeout=3600 \
  --project=shared-playground-414521

# Get URL
gcloud run services describe can-inspection-sim \
  --region=us-central1 \
  --format='value(status.url)'
```

**Limitations**:
- No GPU support
- 60-minute timeout (can extend to 1 hour with --timeout)
- Cold starts

### Option 3: GKE (For Production Scale)

```bash
# Create GKE cluster (if not exists)
gcloud container clusters create can-inspection-cluster \
  --num-nodes=2 \
  --machine-type=n1-standard-2 \
  --zone=us-central1-a

# Get credentials
gcloud container clusters get-credentials can-inspection-cluster \
  --zone=us-central1-a

# Create deployment
kubectl create deployment can-inspection-sim \
  --image=ghcr.io/<your-username>/can-inspection-simulation:latest

# Expose service
kubectl expose deployment can-inspection-sim \
  --type=LoadBalancer \
  --port=8081

# Get external IP
kubectl get service can-inspection-sim
```

## Terraform Deployment

Create `can-inspection.tf`:

```hcl
resource "google_compute_instance" "can_inspection" {
  name         = "can-inspection-sim"
  machine_type = "n1-standard-2"
  zone         = "us-central1-a"

  tags = ["can-inspection"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    gce-container-declaration = <<-EOT
      spec:
        containers:
        - name: can-inspection
          image: ghcr.io/<your-username>/can-inspection-simulation:latest
          stdin: false
          tty: false
        restartPolicy: Always
    EOT
  }
}

resource "google_compute_firewall" "can_inspection_web" {
  name    = "allow-can-inspection-web"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["8081"]
  }

  target_tags   = ["can-inspection"]
  source_ranges = ["0.0.0.0/0"]  # Restrict this in production
}

output "web_viewer_url" {
  value = "http://${google_compute_instance.can_inspection.network_interface[0].access_config[0].nat_ip}:8081"
}
```

Deploy:
```bash
terraform init
terraform apply
terraform output web_viewer_url
```

## Connecting to the Deployment

### Web Viewer (Port 8081)

```bash
# Get instance IP
INSTANCE_IP=$(gcloud compute instances describe can-inspection-sim \
  --zone=us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

# Open in browser
open "http://$INSTANCE_IP:8081"
```

### SSH Access (for debugging)

```bash
# SSH into container
gcloud compute ssh can-inspection-sim --zone=us-central1-a

# Attach to container
docker ps
docker exec -it <container-id> /bin/bash

# Check web viewer logs
docker logs <container-id> | grep web_viewer
```

## Ports Exposed

| Port | Service | Description |
|------|---------|-------------|
| 8081 | Web Viewer | Flask-based camera view |
| 8080 | Viam Web UI | Viam robot management |
| 8443 | Viam gRPC | Viam API endpoint |
| 22 | SSH | Container SSH (if needed) |

## Monitoring and Troubleshooting

### Check if container is running

```bash
gcloud compute ssh can-inspection-sim --zone=us-central1-a \
  --command="docker ps"
```

### View logs

```bash
gcloud compute ssh can-inspection-sim --zone=us-central1-a \
  --command="docker logs \$(docker ps -q)"
```

### Test web viewer locally

```bash
curl -I http://$INSTANCE_IP:8081
```

Should return `200 OK` with `Content-Type: text/html`.

### Common Issues

**"Connection refused" on port 8081**:
- Check firewall rule: `gcloud compute firewall-rules describe allow-can-inspection-web`
- Verify container is running: `docker ps`
- Check web_viewer.py is running: `docker logs | grep "Running on"`

**Simulation not rendering**:
- Check if xvfb is running: `ps aux | grep Xvfb`
- GPU not available: Consider adding GPU to instance
- Check Gazebo logs: `docker logs | grep "gz sim"`

**Can't pull image**:
- Make sure package is public on GitHub
- Or authenticate: `docker login ghcr.io -u <username> -p <PAT>`

## Cost Estimates

| Configuration | Monthly Cost |
|--------------|--------------|
| n1-standard-2 (no GPU) | ~$60 |
| n1-standard-4 + T4 GPU | ~$230 |
| Cloud Run (sporadic use) | ~$5-20 |
| GKE cluster (2 nodes) | ~$150 |

## Security Hardening

**For production**:

1. **Restrict firewall**:
   ```bash
   gcloud compute firewall-rules update allow-can-inspection-web \
     --source-ranges="YOUR_IP/32"
   ```

2. **Add authentication** to web viewer (modify web_viewer.py):
   ```python
   from flask import request

   @app.before_request
   def check_auth():
       auth = request.headers.get('Authorization')
       if auth != 'Bearer YOUR_SECRET':
           return 'Unauthorized', 401
   ```

3. **Use HTTPS** with load balancer or Caddy reverse proxy

4. **VPC isolation**: Deploy in private subnet with Cloud NAT

## Next Steps

1. **Push workflow to GitHub**: The workflow will automatically build on push
2. **Wait for build**: Check Actions tab on GitHub (~5-10 minutes)
3. **Deploy to GCP**: Use one of the deployment options above
4. **Access web viewer**: Navigate to http://INSTANCE_IP:8081
5. **Configure Viam** (optional): Mount viam config for robot integration

## Example: Complete Deployment

```bash
#!/bin/bash
set -e

# Configuration
PROJECT_ID="shared-playground-414521"
ZONE="us-central1-a"
IMAGE="ghcr.io/<your-username>/can-inspection-simulation:latest"

# 1. Create firewall rule
gcloud compute firewall-rules create allow-can-inspection-web \
  --allow tcp:8081 \
  --target-tags=can-inspection \
  --project=$PROJECT_ID \
  2>/dev/null || echo "Firewall rule already exists"

# 2. Create instance with container
gcloud compute instances create-with-container can-inspection-sim \
  --container-image=$IMAGE \
  --machine-type=n1-standard-2 \
  --tags=can-inspection \
  --zone=$ZONE \
  --project=$PROJECT_ID

# 3. Wait for instance to be ready
echo "Waiting for instance to start..."
sleep 30

# 4. Get IP and test
INSTANCE_IP=$(gcloud compute instances describe can-inspection-sim \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "✅ Deployment complete!"
echo "Web viewer: http://$INSTANCE_IP:8081"
echo ""
echo "Testing connection..."
curl -I "http://$INSTANCE_IP:8081" || echo "⚠️  Wait a minute for container to fully start"
```

Save as `deploy-to-gcp.sh`, make executable, and run:
```bash
chmod +x deploy-to-gcp.sh
./deploy-to-gcp.sh
```

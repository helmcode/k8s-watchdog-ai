.PHONY: build clean test docker-build deploy undeploy help

# Variables
BINARY_NAME=observer
DOCKER_IMAGE=helmcloud/k8s-observer
DOCKER_TAG=latest

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build the binary
	@echo "Building $(BINARY_NAME)..."
	@go build -o bin/$(BINARY_NAME) ./cmd/observer
	@echo "Binary built: bin/$(BINARY_NAME)"

run: build ## Build and run in normal mode
	@echo "Running $(BINARY_NAME)..."
	@./bin/$(BINARY_NAME)

test-report: build ## Build and run in test report mode
	@echo "Running $(BINARY_NAME) in test report mode..."
	@./bin/$(BINARY_NAME) --test-report

clean: ## Clean build artifacts
	@echo "Cleaning..."
	@rm -rf bin/
	@rm -f *.db *.db-shm *.db-wal
	@echo "Clean complete"

test: ## Run tests
	@echo "Running tests..."
	@go test -v ./...

docker-build: ## Build Docker image
	@echo "Building Docker image $(DOCKER_IMAGE):$(DOCKER_TAG)..."
	@docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	@echo "Docker image built successfully"

docker-push: docker-build ## Build and push Docker image
	@echo "Pushing Docker image $(DOCKER_IMAGE):$(DOCKER_TAG)..."
	@docker push $(DOCKER_IMAGE):$(DOCKER_TAG)
	@echo "Docker image pushed successfully"

deploy: ## Deploy to Kubernetes
	@echo "Deploying to Kubernetes..."
	@kubectl apply -f manifests/
	@echo "Deployment complete"

undeploy: ## Remove from Kubernetes
	@echo "Removing from Kubernetes..."
	@kubectl delete -f manifests/
	@echo "Removal complete"

logs: ## Show logs from running pod
	@kubectl logs -l app=k8s-observer -f

status: ## Show deployment status
	@echo "Deployment status:"
	@kubectl get pods -l app=k8s-observer
	@echo ""
	@echo "ConfigMap:"
	@kubectl get configmap k8s-observer-config
	@echo ""
	@echo "Secret:"
	@kubectl get secret k8s-observer-secrets

mod-tidy: ## Tidy Go modules
	@echo "Tidying Go modules..."
	@go mod tidy
	@echo "Go modules tidied"

fmt: ## Format Go code
	@echo "Formatting code..."
	@go fmt ./...
	@echo "Code formatted"

vet: ## Run go vet
	@echo "Running go vet..."
	@go vet ./...
	@echo "go vet complete"

lint: fmt vet ## Run formatters and linters
	@echo "Linting complete"

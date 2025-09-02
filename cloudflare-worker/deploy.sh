#!/bin/bash

# Cloudflare Worker Deployment Script for Quill Auto Blogger
# This script automates the deployment process for different environments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command_exists wrangler; then
        print_error "Wrangler CLI not found. Please install it first:"
        echo "npm install -g wrangler"
        exit 1
    fi
    
    if ! command_exists node; then
        print_error "Node.js not found. Please install Node.js first."
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to validate configuration
validate_config() {
    print_status "Validating configuration..."
    
    if [ ! -f "wrangler.toml" ]; then
        print_error "wrangler.toml not found in current directory"
        exit 1
    fi
    
    if [ ! -f "worker.js" ]; then
        print_error "worker.js not found in current directory"
        exit 1
    fi
    
    print_success "Configuration validation passed"
}

# Function to deploy to specific environment
deploy_environment() {
    local env=$1
    local env_name=""
    
    case $env in
        "dev"|"development")
            env_name=""
            print_status "Deploying to development environment..."
            ;;
        "staging")
            env_name="staging"
            print_status "Deploying to staging environment..."
            ;;
        "prod"|"production")
            env_name="production"
            print_status "Deploying to production environment..."
            ;;
        *)
            print_error "Invalid environment: $env"
            echo "Valid environments: dev, staging, prod"
            exit 1
            ;;
    esac
    
    if [ -n "$env_name" ]; then
        wrangler deploy --env "$env_name"
    else
        wrangler deploy
    fi
    
    print_success "Deployment to $env environment completed"
}

# Function to set secrets
set_secrets() {
    print_status "Setting secrets..."
    
    if [ -z "$WORKER_BEARER_TOKEN" ]; then
        print_warning "WORKER_BEARER_TOKEN not set. You may need to set it manually:"
        echo "wrangler secret put WORKER_BEARER_TOKEN"
    else
        echo "$WORKER_BEARER_TOKEN" | wrangler secret put WORKER_BEARER_TOKEN
        print_success "WORKER_BEARER_TOKEN secret set"
    fi
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    
    # Test the worker locally
    if [ "$1" = "dev" ] || [ "$1" = "development" ]; then
        print_status "Starting local development server..."
        wrangler dev &
        local pid=$!
        
        # Wait for server to start
        sleep 5
        
        # Test health endpoint
        if curl -s http://localhost:8787/health > /dev/null; then
            print_success "Local development server is running"
        else
            print_error "Local development server failed to start"
            kill $pid 2>/dev/null || true
            exit 1
        fi
        
        # Stop local server
        kill $pid 2>/dev/null || true
    fi
    
    print_success "Tests completed"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] ENVIRONMENT"
    echo ""
    echo "Environments:"
    echo "  dev, development    Deploy to development"
    echo "  staging            Deploy to staging"
    echo "  prod, production   Deploy to production"
    echo ""
    echo "Options:"
    echo "  -h, --help         Show this help message"
    echo "  -s, --set-secrets  Set secrets before deployment"
    echo "  -t, --test         Run tests before deployment"
    echo "  -v, --verbose      Verbose output"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Deploy to development"
    echo "  $0 -s -t staging          # Set secrets, run tests, deploy to staging"
    echo "  $0 --set-secrets prod     # Set secrets and deploy to production"
}

# Main script
main() {
    local environment=""
    local set_secrets_flag=false
    local test_flag=false
    local verbose=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -s|--set-secrets)
                set_secrets_flag=true
                shift
                ;;
            -t|--test)
                test_flag=true
                shift
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                if [ -z "$environment" ]; then
                    environment=$1
                else
                    print_error "Multiple environments specified"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # Check if environment is specified
    if [ -z "$environment" ]; then
        print_error "Environment not specified"
        show_usage
        exit 1
    fi
    
    # Set verbose mode if requested
    if [ "$verbose" = true ]; then
        set -x
    fi
    
    print_status "Starting deployment process..."
    
    # Run checks and deployment
    check_prerequisites
    validate_config
    
    if [ "$set_secrets_flag" = true ]; then
        set_secrets
    fi
    
    if [ "$test_flag" = true ]; then
        run_tests "$environment"
    fi
    
    deploy_environment "$environment"
    
    print_success "Deployment process completed successfully!"
}

# Run main function with all arguments
main "$@"

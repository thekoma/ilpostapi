#!/bin/sh
set -e

SECRET_NAME="ilpost-api-credentials"
NAMESPACE="${SKAFFOLD_NAMESPACE:-default}"
EXAMPLE_FILE="deploy/helm/secret.yaml.example"
SECRET_FILE="deploy/helm/secret.yaml"

if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "[ok] Secret '$SECRET_NAME' found in namespace '$NAMESPACE'"
    exit 0
fi

echo ""
echo "============================================================"
echo "  SECRET '$SECRET_NAME' NOT FOUND"
echo "============================================================"
echo ""
echo "  The application requires Il Post credentials to work."
echo ""

if [ -f "$SECRET_FILE" ]; then
    echo "  Found $SECRET_FILE, creating secret..."
    kubectl apply -f "$SECRET_FILE" -n "$NAMESPACE"
    echo ""
    echo "  [ok] Secret created successfully."
    exit 0
fi

echo "  To fix this, choose one of:"
echo ""
echo "  1) Copy the example and fill in your credentials:"
echo "     cp $EXAMPLE_FILE $SECRET_FILE"
echo "     # edit $SECRET_FILE with your credentials"
echo ""
echo "  2) Create the secret directly:"
echo "     kubectl create secret generic $SECRET_NAME \\"
echo "       -n $NAMESPACE \\"
echo "       --from-literal=EMAIL='your-email@domain.com' \\"
echo "       --from-literal=PASSWORD='your-password'"
echo ""
echo "============================================================"
echo ""
exit 1

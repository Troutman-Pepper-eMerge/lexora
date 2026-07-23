1. az login
2. docker buildx build --platform linux/amd64 -t  matterwise2democr-faaegygjb0e2aveb.azurecr.io/matterwise:104 -f Dockerfile .
3. az acr login --name matterwise2democr-faaegygjb0e2aveb.azurecr.io
4. docker push matterwise2democr-faaegygjb0e2aveb.azurecr.io/matterwise:104
5. az containerapp update --name mw-2-demo-dev-ca --resource-group matterwise-2-demo-dev-rg --container-name matterwise --image matterwise2democr-faaegygjb0e2aveb.azurecr.io/matterwise:104
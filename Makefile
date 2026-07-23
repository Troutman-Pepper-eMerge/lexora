REGISTRY      := matterwise2democr-faaegygjb0e2aveb.azurecr.io
IMAGE         := matterwise
ACA_NAME      := mw-2-demo-dev-ca
ACA_RG        := matterwise-2-demo-dev-rg
ACA_CONTAINER := matterwise
TAG           := $(shell git rev-parse --short HEAD)

FULL_IMAGE := $(REGISTRY)/$(IMAGE):$(TAG)

.PHONY: build push update deploy

build:
	docker buildx build --platform linux/amd64 -t $(FULL_IMAGE) -f Dockerfile .

push:
	az acr login --name $(REGISTRY)
	docker push $(FULL_IMAGE)

update:
	az containerapp update \
		--name $(ACA_NAME) \
		--resource-group $(ACA_RG) \
		--container-name $(ACA_CONTAINER) \
		--image $(FULL_IMAGE)

deploy: build push update

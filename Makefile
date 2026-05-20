REGISTRY ?= docker.xkqq.top
IMAGE_NAME ?= xingqiux/hermes-agent
IMAGE ?= $(REGISTRY)/$(IMAGE_NAME)
REF ?= main
PLATFORM ?= linux/amd64
REMOTE ?= xkqq
REMOTE_DIR ?= /home/ziyu/services/hermes-agent
REMOTE_DATA_DIR ?= /home/ziyu/services/hermes-agent-data
REMOTE_UID ?= 1001
REMOTE_GID ?= 1001

COMMIT := $(shell git rev-parse HEAD)
SHORT_COMMIT := $(shell git rev-parse --short HEAD)
TAG ?= $(SHORT_COMMIT)

.PHONY: help status check-clean pull build push publish deploy update

help:
	@echo "Hermes localized Docker workflow"
	@echo "  make status   - show git and image settings"
	@echo "  make pull     - fetch/rebase $(REF) from origin"
	@echo "  make build    - build $(IMAGE):$(TAG) and :latest for $(PLATFORM)"
	@echo "  make push     - push $(IMAGE):$(TAG) and :latest"
	@echo "  make publish  - build and push"
	@echo "  make deploy   - copy compose to $(REMOTE), pull image, docker compose up -d"
	@echo "  make update   - pull, publish, deploy"

status:
	@git status --short --branch
	@echo "IMAGE=$(IMAGE)"
	@echo "TAG=$(TAG)"
	@echo "COMMIT=$(COMMIT)"
	@echo "PLATFORM=$(PLATFORM)"
	@echo "REMOTE=$(REMOTE):$(REMOTE_DIR)"

check-clean:
	@test -z "$$(git status --porcelain)" || (git status --short && echo "Working tree must be clean before publishing/deploying." >&2 && exit 1)

pull: check-clean
	git fetch origin $(REF)
	git rebase origin/$(REF)

build:
	docker buildx build \
		--platform $(PLATFORM) \
		--build-arg HERMES_BUILD_COMMIT=$(COMMIT) \
		--build-arg HERMES_BUILD_REF=$(REF) \
		--build-arg HERMES_BUILD_REMOTE=https://github.com/xingqiux/hermes-agent.git \
		-t $(IMAGE):$(TAG) \
		-t $(IMAGE):latest \
		--load \
		.

push:
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest

publish: check-clean build push

deploy:
	ssh $(REMOTE) 'mkdir -p $(REMOTE_DIR) $(REMOTE_DATA_DIR)'
	scp docker-compose.xkqq.yml $(REMOTE):$(REMOTE_DIR)/docker-compose.yml
	ssh $(REMOTE) 'cd $(REMOTE_DIR) && HERMES_IMAGE=$(IMAGE):latest HERMES_DATA_DIR=$(REMOTE_DATA_DIR) HERMES_UID=$(REMOTE_UID) HERMES_GID=$(REMOTE_GID) docker compose pull && HERMES_IMAGE=$(IMAGE):latest HERMES_DATA_DIR=$(REMOTE_DATA_DIR) HERMES_UID=$(REMOTE_UID) HERMES_GID=$(REMOTE_GID) docker compose up -d'

update: pull publish deploy

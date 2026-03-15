PYTHON ?= python
UVICORN ?= uvicorn

.PHONY: run regress llm llm-regress check

run:
	$(UVICORN) agent.app:app --host 127.0.0.1 --port 8000 --reload

regress:
	AGENT_MODE=regression $(UVICORN) agent.app:app --host 127.0.0.1 --port 8000 --reload

llm:
	AGENT_BACKEND=openai $(UVICORN) agent.app:app --host 127.0.0.1 --port 8000 --reload

llm-regress:
	AGENT_BACKEND=openai AGENT_MODE=regression $(UVICORN) agent.app:app --host 127.0.0.1 --port 8000 --reload

check:
	evalview check tests

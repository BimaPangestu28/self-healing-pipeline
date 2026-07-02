# How to Update System Prompt

This repo contains several agents:
1. Router Agent
2. Elasticsearch Agent
3. K8S Monitor Agent
4. RAG Agent
5. Synthesizer Agent

Each agents have their own system prompt. You could see their system prompt in this repo at `src/config/prompts` folder. This system prompt should be installed in langfuse website. Here is the tutorial to install the system prompt.

1. Open Langfuse in the browser -> Click Go to project.
   ![](../assets/prompt/00_prompt.png)
2. Click Prompts on the left panel -> Click New Prompt.
   ![](../assets/prompt/01_prompt.png)
3. Fill in the Name with the agent's name and `Text Prompt` with the agent's prompt.
   ![](../assets/prompt/02_prompt.png)
4. Checklist the `Set the "production" label` -> Click `Create Prompt`.
   ![](../assets/prompt/03_prompt.png)
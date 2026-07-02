# How to Deploy Model in Azure Foundry

1. Open [https://ai.azure.com](https://www.ai.azure.com) website.
2. Click model catalog -> search the model name on search bar.
   ![](../assets/model/01_model.png)
3. Click Use this model
   ![](../assets/model/02_model.png)
4. CLick customize if you want to edit the default settings -> Click Deploy
   ![](../assets/model/03_model.png)
5. Copy the `Endpoint` and API Key into your clipbooard.
   ![](../assets/model/08_model.png)
6. Check the deployed model on `Models + endpoints` menu.
   ![](../assets/model/04_model.png)

# How to Add the Deployed Model into the Agent Framework

1. Open the AIOps UI -> Click Add Model
   ![](../assets/model/09_model.png)
2. Fill in the model name and paste the `Endpoint` and `API Key` into the form -> Click Save
   ![](../assets/model/10_model.png)
3. Now the model is added and  you could click select to use it as your RCA model.
   ![](../assets/model/11_model.png)

# How to Trace Model in Langfuse
1. Open Langfuse -> Click `Settings` on the left panel -> Click `Model Definitions` -> Click `Add Model Definition`
   ![](../assets/model/05_model.png)
2. Fill in the model name form.
   ![](../assets/model/06_model.png)
3. Fill in the input and output token price form.
   ![](../assets/model/07_model.png)
4. Click Submit
5. Click `Tracing` menu on the left panel -> Click one of the chats from the chat history.
   ![](../assets/model/12_model.png)
6. In this example, notice that `elastic-search-agent` and `synthetizer-agent` use `gpt-4.1` model, while the other use `gpt-4.1-mini` model. The  `elastic-search-agent` and `synthetizer-agent` use the model selected on AIOps UI while the others agents use the model defined at the `.env` file. The `elastic-search-agent` and `synthetizer-agent` use `gpt-4.1` model for the root cause analysis purpose, while the other use `gpt-4.1-mini` for classifying task.
   ![](../assets/model/13_model.png)
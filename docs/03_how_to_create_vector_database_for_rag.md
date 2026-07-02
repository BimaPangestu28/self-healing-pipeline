# How to Create a Vector Database for RAG

## Deploying an Embedding Model in Microsoft Foundry

1. Open [https://ai.azure.com](https://www.ai.azure.com) website.
2. Click on `Models + endpoints` -> CLick Deploy Model -> Click base model.
   ![](../assets/rag/00_embed.png)
3. Filter embedding models to get list of embedding models. In this example, we use `text-embedding-3-small` model -> Click Confirm
   ![](../assets/rag/01_embed.png)
4. Edit the form if you need to customize the model -> Click Deploy.
5. If you've already got the endpoint and API Key from the tutorial `/docs/how/to_deploy_and_trace_model.md`, you could set the `.env` variable based on that value.
   ```env
   AZURE_OPENAI_ENDPOINT=https://aiops-foundry-resource.openai.azure.com/
   AZURE_OPENAI_API_KEY=<Your API KEY>
   ```
6. Fill in the `.env` file variables as below.
   ```env
   AZURE_OPENAI_EMBEDDING_MODEL_NAME=text-embedding-3-small
   AZURE_OPENAI_EMBEDDING_MODEL_VERSION=2023-05-15
   ```

## Preparing the Vector Database in AI Search Platform

1. Open [https://portal.azure.com](https://www.portal.azure.com) -> Click AI Search
   ![](../assets/rag/00_search.png)
2. If you haven't created the resource -> Click create
   ![](../assets/rag/01_search.png)
3. Fill in the form and click `Review + create`.
   ![](../assets/rag/02_search.png)
4. Once you've created the resource, you will be redirected to AI Search Platform's main page. Click the resource link.
   ![](../assets/rag/03_search.png)
5. Click add index
   ![](../assets/rag/04_search.png)
6. Fill in the index name and click `Add field`
   ![](../assets/rag/05_search.png)
7. Fill in the field name. In this example, the field name is `app` and the type is `Edm.string`. Then, click `save`. Do the same thing for other string field such as `error`, `severity`, `category`, and `explanation`.
   ![](../assets/rag/06_search.png)
8. For the vector field, in this example, we will vectorize the `error` field. Therefore, we create `vector_error` field name, `Collection(Edm.Single)` type, and dimensions `1536`.
   ![](../assets/rag/07_search.png)
9. Click create vector search profile.
    ![](../assets/rag/08_search.png)
10. Click create algorithm.
    ![](../assets/rag/09_search.png)
11. Use the default configurations and click save.
    ![](../assets/rag/10_search.png)
12. Once redirected to the previous menu, click `save`.
    ![](../assets/rag/11_search.png)
13. Below is the example of all prepared field. Click `Create`.
    ![](../assets/rag/12_search.png).
14. Once the index is created, click `Indexes` on the left panel.
    
    ![](../assets/rag/13_search.png)
15. Now, the created index will appears on the right column.
    ![](../assets/rag/14_search.png)
16. If you click the index link, you will be directed to the new page.
    ![](../assets/rag/17_search.png)
17. Now, click `Keys` on the left panel.
    ![](../assets/rag/15_search.png)
18. Copy the primary key.
    ![](../assets/rag/16_search.png)
19. Fill in the `.env` variables as follow. For the `API version`, click this link to get the latest version of AI Search platform [Learn Microsoft](https://learn.microsoft.com/en-us/rest/api/searchservice/search-service-api-versions).
    ```env
    AZURE_AI_SEARCH_SERVICE_NAME=aiops-aisearch-resource
    AZURE_AI_SEARCH_INDEX_NAME=aiops-index
    AZURE_SEARCH_API_KEY=<primary key>
    AZURE_AI_SEARCH_API_VERSION=2025-09-01
    ```
    
    Note:
    - `AZURE_SEARCH_API_KEY` can be replaced with `AZURE_AI_SEARCH_API_KEY`.
    - `AZURE_AI_SEARCH_API_VERSION` defaults to `2024-07-01` if omitted.
-  
## Preparing the RAG Dataset

1. Embed the dataset 
   
   Create a JSON file inside `/data` folder. In this example, we use `/data/errors_dataset.json`. Input JSON must be an array of objects. Pick the field you want to vectorize, such as `error`. Each row contains several items, e.g:
    ```JSON
    [{
        "id": 1,
        "app": "aka-be-obe-stg",
        "error": "Bad Request Error - 400",
        "severity": "LOW",
        "category": "input_validation",
        "explanation": "The request payload or parameters are invalid and trigger a 400 response."
    },
    ]
    ```

    To embed the dataset, run:

    ```bash
    uv run python rag/embed.py data/errors_dataset.json error
    ```

    This writes a new file beside the source dataset, for example:

    ```text
    data/vectorized_errors_dataset.json
    ```

    If you embed the `error` field, each row will contain `vector_error`. If you embed `category`, each row will contain `vector_category`.

2. Upload the Vectorized Dataset
   
   Make sure your Azure AI Search index schema already includes the fields in the JSON file, including the matching vector field such as `vector_error`.

    Run:

    ```bash
    uv run python rag/upload.py data/vectorized_errors_dataset.json
    ```

    The script prints the Azure AI Search indexing response as JSON.

3. Once the vector dataset is uploaded, you could see them at `portal.azure.com` -> Click AI Search -> Click Resource Name (e.g `aiops-aisearch-resource`) -> Click Indexes on the left panel -> Click index name (e.g aiops-index) -> click `Search`.
   ![](../assets/rag/17_search.png)

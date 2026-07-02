# Panduan Pembaruan Prompt Sistem, Deploy Model, dan Pembuatan Vector Database untuk RAG

## Overview

Secara umum, AI Agent di repo ini bekerja dengan cara menerima alert, menentukan tools yang tepat untuk analisis alert, menganalisis alert, dan mengirim hasil analisisnya ke telegram.

Tugas masing-masing agent:
1. Router Agent: Mengklasifikasikan intent user dan menentukan target agent (`kubernetes_monitoring`, `elasticsearch`, `rag`) serta mode eksekusi (`single`, `multi`, `clarify`, `reject`, `intro`) tanpa melakukan analisis.
2. Elasticsearch Agent: Mencari dan menganalisis log di Elasticsearch/ELK (list indeks, search log, ambil dokumen by `_id`), menemukan pola error, ringkasan akar masalah, dan langkah lanjut.
3. K8S Monitor Agent: Memantau kondisi Kubernetes secara read-only (cluster/deployment/pod logs), menilai kesehatan, mengelompokkan pod anomalous vs normal, dan memberi rekomendasi tindak lanjut.
4. RAG Agent: Mengambil referensi error paling mirip dari indeks RAG untuk menilai severity dan memberikan penjelasan singkat serta rekomendasi.
5. Synthesizer Agent: Menggabungkan output agent spesialis menjadi jawaban ringkas, konsisten, dan terstruktur (termasuk format khusus untuk alert).

Hasil analisis AI Agent bergantung pada input log error. Oleh karena itu, detil log error akan sangat membantu AI Agent dalam menganalisisnya. Tips untuk memperkuat hasil analisis adalah dengan menggunakan logger bawaan kode pemrograman aplikasi dan menambahkan konteks di pesan error. Konteks error bisa berupa nama class tempat lokasi error ditulis dan menyertakan stacktrace.

AI Agent menggunakan model LLM yang di deploy di Microsoft Foundry. Secara default, ada dua model yang dipasang yakni model reasoning (GPT-4.1) dan model klasifikasi (GPT-4.1-mini). Model reasoning dipakai oleh  elastic-search-agent dan synthetizer-agent. Model klasifikasi dipakai oleh router-agent, k8s-monitor-agent, dan rag-agent. Model reasoning bisa diganti melalui UI, sementara model klasifikasi diganti di file `.env` melalui variabel `AZURE_OPENAI_CLASSIFIER_DEPLOYMENT`.

Vector database dibangun untuk menyimpan data log error beserta severity-nya. Vector database ini akan dimanfaatkan oleh sistem Retrieval-Augmented Generation(RAG). RAG Agent akan mengambil referensi error paling mirip dari vektor database untuk menilai severity dan memberikan penjelasan singkat serta rekomendasi.

Panduan ini memberi petunjuk cara memperbarui system prompt di AI Agent, mendeploy model di Microsoft Foundry, dan membuat vector database.

## Cara Memperbarui Prompt Sistem

Setiap agent memiliki prompt sistem masing-masing. Anda bisa melihat prompt sistemnya di repositori ini pada folder `src/config/prompts`. Prompt sistem tersebut harus diinstal di situs Langfuse. Berikut tutorial untuk menginstal prompt sistem.

1. Buka Langfuse di browser -> Klik Go to project.
   ![](../assets/prompt/00_prompt.png)
2. Klik Prompts di panel kiri -> Klik New Prompt.
   ![](../assets/prompt/01_prompt.png)
3. Isi Name dengan nama agent dan `Text Prompt` dengan prompt agent.
   ![](../assets/prompt/02_prompt.png)
4. Centang `Set the "production" label` -> Klik `Create Prompt`.
   ![](../assets/prompt/03_prompt.png)

## Cara Deploy Model di Azure Foundry

1. Buka situs [https://ai.azure.com](https://www.ai.azure.com).
2. Klik model catalog -> cari nama model di kolom pencarian.
   ![](../assets/model/01_model.png)
3. Klik Use this model
   ![](../assets/model/02_model.png)
4. Klik customize jika ingin mengubah pengaturan default -> Klik Deploy
   ![](../assets/model/03_model.png)
5. Salin `Endpoint` dan API Key ke clipboard Anda.
   ![](../assets/model/08_model.png)
6. Cek model yang sudah dideploy pada menu `Models + endpoints`.
   ![](../assets/model/04_model.png)

## Cara Menambahkan Model yang Dideploy ke Agent Framework

1. Buka AIOps UI -> Klik Add Model
   ![](../assets/model/09_model.png)
2. Isi nama model dan tempelkan `Endpoint` serta `API Key` ke formulir -> Klik Save
   ![](../assets/model/10_model.png)
3. Sekarang model sudah ditambahkan dan Anda bisa klik select untuk menggunakannya sebagai model RCA.
   ![](../assets/model/11_model.png)

## Cara Melacak Model di Langfuse

1. Buka Langfuse -> Klik `Settings` pada panel kiri -> Klik `Model Definitions` -> Klik `Add Model Definition`
   ![](../assets/model/05_model.png)
2. Isi formulir nama model.
   ![](../assets/model/06_model.png)
3. Isi formulir harga token input dan output.
   ![](../assets/model/07_model.png)
4. Klik Submit
5. Klik menu `Tracing` pada panel kiri -> Klik salah satu chat dari riwayat chat.
   ![](../assets/model/12_model.png)
6. Pada contoh ini, perhatikan bahwa `elastic-search-agent` dan `synthetizer-agent` menggunakan model `gpt-4.1`, sedangkan agent lainnya menggunakan `gpt-4.1-mini`. `elastic-search-agent` dan `synthetizer-agent` menggunakan model yang dipilih pada AIOps UI, sedangkan agent lainnya menggunakan model yang didefinisikan pada file `.env`. `elastic-search-agent` dan `synthetizer-agent` menggunakan `gpt-4.1` untuk keperluan root cause analysis, sedangkan yang lain menggunakan `gpt-4.1-mini` untuk klasifikasi tugas.
   ![](../assets/model/13_model.png)

## Cara Membuat Vector Database untuk RAG

### Deploy Model Embedding di Microsoft Foundry

1. Buka situs [https://ai.azure.com](https://www.ai.azure.com).
2. Klik `Models + endpoints` -> Klik Deploy Model -> Klik base model.
   ![](../assets/rag/00_embed.png)
3. Filter model embedding untuk mendapatkan daftar model embedding. Pada contoh ini, gunakan model `text-embedding-3-small` -> Klik Confirm
   ![](../assets/rag/01_embed.png)
4. Edit formulir jika perlu menyesuaikan model -> Klik Deploy.
5. Jika Anda sudah mendapatkan endpoint dan API Key dari tutorial `/docs/how/to_deploy_and_trace_model.md`, Anda bisa mengatur variabel `.env` berdasarkan nilai tersebut.
   ```env
   AZURE_OPENAI_ENDPOINT=https://aiops-foundry-resource.openai.azure.com/
   AZURE_OPENAI_API_KEY=<Your API KEY>
   ```
6. Isi variabel pada file `.env` seperti di bawah.
   ```env
   AZURE_OPENAI_EMBEDDING_MODEL_NAME=text-embedding-3-small
   AZURE_OPENAI_EMBEDDING_MODEL_VERSION=2023-05-15
   ```

### Menyiapkan Vector Database di AI Search Platform

1. Buka [https://portal.azure.com](https://www.portal.azure.com) -> Klik AI Search
   ![](../assets/rag/00_search.png)
2. Jika belum membuat resource -> Klik create
   ![](../assets/rag/01_search.png)
3. Isi formulir dan klik `Review + create`.
   ![](../assets/rag/02_search.png)
4. Setelah resource dibuat, Anda akan diarahkan ke halaman utama AI Search Platform. Klik tautan resource.
   ![](../assets/rag/03_search.png)
5. Klik add index
   ![](../assets/rag/04_search.png)
6. Isi nama index dan klik `Add field`
   ![](../assets/rag/05_search.png)
7. Isi nama field. Pada contoh ini, nama field adalah `app` dan tipenya `Edm.string`. Lalu klik `save`. Lakukan hal yang sama untuk field string lain seperti `error`, `severity`, `category`, dan `explanation`.
   ![](../assets/rag/06_search.png)
8. Untuk field vektor, pada contoh ini kita akan memvektorkan field `error`. Karena itu, buat field bernama `vector_error`, tipe `Collection(Edm.Single)`, dan dimensi `1536`.
   ![](../assets/rag/07_search.png)
9. Klik create vector search profile.
   ![](../assets/rag/08_search.png)
10. Klik create algorithm.
    ![](../assets/rag/09_search.png)
11. Gunakan konfigurasi default lalu klik save.
    ![](../assets/rag/10_search.png)
12. Setelah kembali ke menu sebelumnya, klik `save`.
    ![](../assets/rag/11_search.png)
13. Berikut contoh semua field yang sudah disiapkan. Klik `Create`.
    ![](../assets/rag/12_search.png).
14. Setelah index dibuat, klik `Indexes` pada panel kiri.

    ![](../assets/rag/13_search.png)
15. Sekarang index yang dibuat akan muncul di kolom kanan.
    ![](../assets/rag/14_search.png)
16. Jika Anda klik tautan index, Anda akan diarahkan ke halaman baru.
    ![](../assets/rag/17_search.png)
17. Sekarang, klik `Keys` pada panel kiri.
    ![](../assets/rag/15_search.png)
18. Salin primary key.
    ![](../assets/rag/16_search.png)
19. Isi variabel `.env` sebagai berikut. Untuk `API version`, klik tautan ini untuk mendapatkan versi terbaru dari AI Search platform [Learn Microsoft](https://learn.microsoft.com/en-us/rest/api/searchservice/search-service-api-versions).
    ```env
    AZURE_AI_SEARCH_SERVICE_NAME=aiops-aisearch-resource
    AZURE_AI_SEARCH_INDEX_NAME=aiops-index
    AZURE_SEARCH_API_KEY=<primary key>
    AZURE_AI_SEARCH_API_VERSION=2025-09-01
    ```

    Catatan:
    - `AZURE_SEARCH_API_KEY` bisa diganti dengan `AZURE_AI_SEARCH_API_KEY`.
    - `AZURE_AI_SEARCH_API_VERSION` default ke `2024-07-01` jika tidak diisi.
-  
### Menyiapkan Dataset RAG

1. Embed dataset
   
   Buat file JSON di dalam folder `/data`. Pada contoh ini, gunakan `/data/errors_dataset.json`. Input JSON harus berupa array objek. Pilih field yang ingin divektorkan, seperti `error`. Setiap baris berisi beberapa item, misalnya:
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

    Untuk melakukan embedding dataset, jalankan:

    ```bash
    uv run python rag/embed.py data/errors_dataset.json error
    ```

    Ini akan menulis file baru di samping dataset sumber, misalnya:

    ```text
    data/vectorized_errors_dataset.json
    ```

    Jika Anda melakukan embedding pada field `error`, setiap baris akan berisi `vector_error`. Jika embedding pada `category`, setiap baris akan berisi `vector_category`.

2. Unggah Dataset yang Sudah Di-vektorisasi
   
   Pastikan skema index Azure AI Search Anda sudah mencakup field pada file JSON, termasuk field vektor yang sesuai seperti `vector_error`.

    Jalankan:

    ```bash
    uv run python rag/upload.py data/vectorized_errors_dataset.json
    ```

    Script akan menampilkan respons indexing Azure AI Search dalam format JSON.

3. Setelah dataset vektor diunggah, Anda bisa melihatnya di `portal.azure.com` -> Klik AI Search -> Klik Resource Name (misalnya `aiops-aisearch-resource`) -> Klik Indexes pada panel kiri -> Klik nama index (misalnya aiops-index) -> klik `Search`.
   ![](../assets/rag/17_search.png)

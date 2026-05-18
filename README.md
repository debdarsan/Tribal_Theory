conda create -n BIDA python=3.11

conda activate BIDA

pip install -r BIDA_req.txt

streamlit run build_chromadb_v3.py to receate the Chroma DB. Otherwise use the DB in this repo.

streamlit run app.py

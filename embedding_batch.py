import psycopg
import requests
import json

BATCH_LIMIT = 200
TARGET_DOCUMENT_ID = 5

conn=psycopg.connect("postgresql://checker:114514@localhost/postgres")
cur=conn.cursor()
# 鎵归噺鎻掑叆鏁版嵁
cur.execute(
    "select id,content from chunks where embedding is null and document_id = %s limit %s",
    (TARGET_DOCUMENT_ID, BATCH_LIMIT),
)
rows=cur.fetchall()

url="https://api.siliconflow.cn/v1/embeddings"
headers={"Authorization":"Bearer sk-cylgdoagsltmnwzzatmxobtncwjlllmjqqhoywzlveuelfwz","Content-Type":"application/json"}
data={
    "model": "Qwen/Qwen3-Embedding-4B",
    "input": [row[1] for row in rows]
}
response=requests.post(url, headers=headers, json=data)
result=response.json()

for i,(chunk_id,_) in enumerate(rows):
    embedding=result["data"][i]["embedding"]
    cur.execute("update chunks set embedding=%s where id=%s",(json.dumps(embedding) ,chunk_id))
conn.commit()
cur.close()
conn.close()

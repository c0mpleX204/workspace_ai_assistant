from typing import List, Dict, Any, Optional
from infra.db import get_conn


# ───────────────────────── courses ─────────────────────────

def create_course(name: str, term: str | None = None, owner_id: str = "default_user") -> int:
    sql = """
    insert into courses (name, term, owner_id)
    values (%s, %s, %s)
    returning id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name, term, owner_id))
            row = cur.fetchone()
            return int(row[0])


def list_courses(owner_id: str = "default_user", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    sql = """
    select c.id, c.name, c.term, c.owner_id, c.created_at,
           count(distinct d.id) as doc_count,
           min(d.id) as cover_document_id
    from courses c
    left join documents d on d.course_id = c.id
    where c.owner_id = %s
    group by c.id, c.name, c.term, c.owner_id, c.created_at
    order by c.id desc
    limit %s offset %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (owner_id, limit, offset))
            rows = cur.fetchall()
    return [
        {
            "course_id": r[0],
            "name": r[1],
            "term": r[2],
            "owner_id": r[3],
            "created_at": str(r[4]) if r[4] else None,
            "doc_count": int(r[5] or 0),
            "cover_document_id": r[6],
        }
        for r in rows
    ]


def get_course(course_id: int) -> Optional[Dict[str, Any]]:
    sql = """
    select c.id, c.name, c.term, c.owner_id, c.created_at,
           count(distinct d.id) as doc_count
    from courses c
    left join documents d on d.course_id = c.id
    where c.id = %s
    group by c.id, c.name, c.term, c.owner_id, c.created_at
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (course_id,))
            r = cur.fetchone()
    if not r:
        return None
    return {
        "course_id": r[0],
        "name": r[1],
        "term": r[2],
        "owner_id": r[3],
        "created_at": str(r[4]) if r[4] else None,
        "doc_count": int(r[5] or 0),
    }


def update_course(course_id: int, name: str | None = None, term: str | None = None) -> bool:
    sets = []
    params: list = []
    if name is not None:
        sets.append("name = %s")
        params.append(name)
    if term is not None:
        sets.append("term = %s")
        params.append(term)
    if not sets:
        return False
    params.append(course_id)
    sql = f"update courses set {', '.join(sets)} where id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return cur.rowcount > 0


def delete_course(course_id: int) -> bool:
    """级联删除课程下的所有文档和chunks。"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "delete from chunks where document_id in (select id from documents where course_id = %s)",
                (course_id,)
            )
            cur.execute("delete from documents where course_id = %s", (course_id,))
            cur.execute("delete from courses where id = %s", (course_id,))
            return cur.rowcount > 0


def list_chunks_with_embedding_multi(
    document_ids: List[int],
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    """多文档联合检索，返回所有选中文档的已embedding chunks。"""
    if not document_ids:
        return []
    placeholders = ",".join(["%s"] * len(document_ids))
    sql = f"""
    select c.id as chunk_id, c.document_id, c.content,
           c.embedding, c.page_no, d.title as document_title
    from chunks c join documents d on d.id = c.document_id
    where c.embedding is not null
      and c.document_id in ({placeholders})
    order by c.id
    limit %s
    """
    params = list(document_ids) + [limit]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    return [
        {
            "chunk_id": r[0],
            "document_id": r[1],
            "content": r[2],
            "embedding": r[3],
            "page_no": r[4],
            "document_title": r[5],
        }
        for r in rows
    ]

def list_chunks_with_embedding(document_id:int | None =None,limit:int=2000)->list[dict[str,Any]]:
    sql = """
    select c.id as chunk_id, c.document_id,c.content,
    c.embedding,c.page_no,d.title as document_title
    from chunks c join documents d on d.id = c.document_id
    where c.embedding is not null
    """
    params: list[Any] = []
    if document_id is not None:
        sql += " and c.document_id = %s"
        params.append(document_id)
    sql += " order by c.id limit %s"
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows=cur.fetchall()
            result=[]
            for row in rows:
                result.append({
                    "chunk_id":row[0],
                    "document_id":row[1],
                    "content":row[2],
                    "embedding":row[3],
                    "page_no":row[4],
                    "document_title":row[5],
                })
    return result

def create_course(name: str, term: str | None = None, owner_id: str = "default_user") -> int:
    sql = """
    insert into courses (name, term, owner_id)
    values (%s, %s, %s)
    returning id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name, term, owner_id))
            row = cur.fetchone()
            return int(row[0])


def create_document(course_id: int, title: str, file_type: str, source_path: str) -> int:
    sql = """
    insert into documents (course_id, title, file_type, source_path)
    values (%s, %s, %s, %s)
    returning id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (course_id, title, file_type, source_path))
            row = cur.fetchone()
            return int(row[0])


def insert_chunks(document_id: int, chunks: List[Dict[str, Any]]) -> int:
    sql = """
    insert into chunks (document_id, chunk_index, content, token_count, page_no, tags)
    values (%s, %s, %s, %s, %s, %s)
    on conflict (document_id, chunk_index) do update
    set content = excluded.content,
        token_count = excluded.token_count,
        page_no = excluded.page_no,
        tags = excluded.tags
    """
    if not chunks:
        return 0

    rows = [
        (
            document_id,
            int(c["chunk_index"]),
            c["content"],
            int(c.get("token_count", 0)),
            c.get("page_no"),
            c.get("tags"),
        )
        for c in chunks
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)

def list_documents(course_id: int | None=None , limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    limit =int(limit or 20)
    offset =int(offset or 0)
    limit= max(1,min(limit,100))
    offset=max(0,offset)
    sql = """
    select
        d.id,
        d.course_id,
        d.title,
        d.file_type,
        d.source_path,
        d.created_at,
        count(c.id) as chunk_count
    from documents d
    left join chunks c on c.document_id = d.id
    where 1=1
    """
    params: list[Any] = []
    if course_id is not None:
        sql += " and d.course_id = %s"
        params.append(course_id)
    sql += """
    group by d.id, d.course_id, d.title, d.file_type, d.source_path, d.created_at
    order by d.id desc
    limit %s offset %s
    """
    params.extend([limit, offset])
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    "document_id": row[0],
                    "course_id": row[1],
                    "title": row[2],
                    "file_type": row[3],
                    "source_path": row[4],
                    "created_at": row[5],
                    "chunk_count": int(row[6] or 0),
                })
    return result

def get_document_detail(document_id: int) -> dict[str, Any] | None:
    sql = """
    select
        d.id,
        d.course_id,
        d.title,
        d.file_type,
        d.source_path,
        d.created_at,
        count(c.id) as chunk_count
    from documents d
    left join chunks c on c.document_id = d.id
    where d.id = %s
    group by d.id, d.course_id, d.title, d.file_type, d.source_path, d.created_at
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (document_id,))
            row = cur.fetchone()

    if not row:
        return None

    return {
        "document_id": row[0],
        "course_id": row[1],
        "title": row[2],
        "file_type": row[3],
        "source_path": row[4],
        "created_at": row[5],
        "chunk_count": int(row[6] or 0),
    }

def delete_document_with_chunks(document_id: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # 先删子表，避免没有配置级联约束时报外键错误
            cur.execute("delete from chunks where document_id = %s", (document_id,))
            # 再删主表
            cur.execute("delete from documents where id = %s", (document_id,))
            deleted_count = cur.rowcount

    return deleted_count > 0

def list_user_preferences(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    sql = """
        select pref_key, pref_value, source, confidence, updated_at
        from user_preferences
        where user_id = %s
        order by updated_at desc
        limit %s
        """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, limit))
            rows = cur.fetchall()
            result: List[Dict[str, Any]] = []
            for row in rows:
                result.append(
                    {
                        "key": row[0],
                        "value": row[1],
                        "source": row[2],
                        "confidence": float(row[3]) if row[3] is not None else None,
                        "updated_at": str(row[4]) if row[4] is not None else None,
                    }
                )

    return result


def get_user_preference_by_key(user_id: str, key: str) -> Optional[Dict[str, Any]]:
    sql = """
    select pref_key, pref_value, source, confidence, updated_at
    from user_preferences
    where user_id = %s and pref_key = %s
    order by updated_at desc
    limit 1
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, key))
            row = cur.fetchone()

    if not row:
        return None

    return {
        "key": row[0],
        "value": row[1],
        "source": row[2],
        "confidence": float(row[3]) if row[3] is not None else None,
        "updated_at": str(row[4]) if row[4] is not None else None,
    }


def list_user_preferences_by_prefix(
    user_id: str,
    key_prefix: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    sql = """
    select pref_key, pref_value, source, confidence, updated_at
    from user_preferences
    where user_id = %s and pref_key like %s
    order by updated_at desc
    limit %s
    """
    like_pattern = f"{key_prefix}%"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, like_pattern, limit))
            rows = cur.fetchall()

    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "key": row[0],
                "value": row[1],
                "source": row[2],
                "confidence": float(row[3]) if row[3] is not None else None,
                "updated_at": str(row[4]) if row[4] is not None else None,
            }
        )
    return result


def list_learning_progress(
    user_id: str,
    course_id: int | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    sql = """
    select course_id, topic, status, mastery, last_review_at, next_review_at, evidence
    from learning_progress
    where user_id = %s
    """
    params: List[Any] = [user_id]
    if course_id is not None:
        sql += " and course_id = %s"
        params.append(course_id)
    sql += " order by coalesce(next_review_at, now()) asc limit %s"
    params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            result: List[Dict[str, Any]] = []
            for row in rows:
                result.append(
                    {
                        "course_id": row[0],
                        "topic": row[1],
                        "status": row[2],
                        "mastery": float(row[3]) if row[3] is not None else None,
                        "last_review_at": str(row[4]) if row[4] is not None else None,
                        "next_review_at": str(row[5]) if row[5] is not None else None,
                        "evidence": row[6],
                    }
                )

    return result

def upsert_user_preference(user_id: str, key: str, value: str, source: str, confidence: float | None = None) -> bool:
    sql = """
    insert into user_preferences (user_id, pref_key, pref_value, source, confidence,last_seen,hit_count)
    values (%s, %s, %s, %s, %s,now(),1)
    on conflict (user_id, pref_key) do update
    set pref_value = excluded.pref_value,
        source = excluded.source,
        confidence = excluded.confidence,
        last_seen=now(),
        hit_count=coalesce(user_preferences.hit_count,0)+1,
        updated_at = now()
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, key, value, source, confidence))
            return cur.rowcount > 0

def upsert_learning_progress(
    user_id: str,
    course_id: int | None,
    topic: str,
    status: str,
    mastery: float | None = None,
    last_review_at: str | None = None,
    next_review_at: str | None = None,
    evidence: str | None = None,
) -> bool:
    sql = """
    insert into learning_progress (user_id, course_id, topic, status, mastery, last_review_at, next_review_at, evidence)
    values (%s, %s, %s, %s, %s, %s, %s, %s)
    on conflict (user_id, course_id, topic) do update
    set status = excluded.status,
        mastery = excluded.mastery,
        last_review_at = excluded.last_review_at,
        next_review_at = excluded.next_review_at,
        evidence = excluded.evidence,
        updated_at = now()
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    user_id,
                    course_id,
                    topic,
                    status,
                    mastery,
                    last_review_at,
                    next_review_at,
                    evidence,
                ),
            )
            return cur.rowcount > 0
        
def list_due_reminders(window_minutes: int = 60, limit: int = 200) -> List[Dict[str, Any]]:
    """
    返回 next_review_at 在 now() 到 now() + window_minutes 之间的记录。
    返回字段包含 user_id, course_id, topic, next_review_at, evidence
    """
    sql = """
    select user_id, course_id, topic, status, mastery, next_review_at, evidence
    from learning_progress
    where next_review_at is not null
      and next_review_at <= now() + (%s || ' minutes')::interval
      and next_review_at >= now()
    order by next_review_at asc
    limit %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (str(window_minutes), limit))
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    "user_id": row[0],
                    "course_id": row[1],
                    "topic": row[2],
                    "status": row[3],
                    "mastery": float(row[4]) if row[4] is not None else None,
                    "next_review_at": str(row[5]) if row[5] is not None else None,
                    "evidence": row[6],
                })
    return result


def mark_reminder_sent(user_id: str, course_id: int | None, topic: str, at_time) -> bool:
    """
    更新 learning_progress.last_reminded_at，作为已提醒标识。
    """
    sql = """
    update learning_progress
    set last_reminded_at = %s, updated_at = now()
    where user_id = %s and topic = %s and (course_id = %s or (course_id is null and %s is null))
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (at_time, user_id, topic, course_id, course_id))
            return cur.rowcount > 0


def list_user_reminders(user_id: str, lookahead_hours: int = 48, limit: int = 50) -> List[Dict[str, Any]]:
    """
    返回用户未来 lookahead_hours 小时内的 reminders，供会话注入使用。
    """
    sql = """
    select course_id, topic, status, mastery, next_review_at, evidence
    from learning_progress
    where user_id = %s
      and next_review_at is not null
      and next_review_at <= now() + (%s || ' hours')::interval
      and (last_reminded_at is null OR last_reminded_at < now() - interval '1 hour')
    order by next_review_at asc
    limit %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, str(lookahead_hours), limit))
            rows = cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    "course_id": row[0],
                    "topic": row[1],
                    "status": row[2],
                    "mastery": float(row[3]) if row[3] is not None else None,
                    "next_review_at": str(row[4]) if row[4] is not None else None,
                    "evidence": row[5],
                })
    return result



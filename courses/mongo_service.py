"""
Service layer untuk integrasi MongoDB.

Dua collection dipakai:
- activity_logs       -> Activity Log (setiap aksi user: view, enroll, comment)
- learning_analytics   -> Learning Analytics (snapshot progres belajar per enrollment)
"""
from datetime import datetime
from pymongo import MongoClient

from django.conf import settings

_client = None


def get_mongo_client():
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI)
    return _client


def get_mongo_db():
    return get_mongo_client()[settings.MONGO_DB_NAME]


# ── Activity Log ──────────────────────────────────────────────

def log_activity(user_id: int, action: str, target_type: str = None,
                  target_id: int = None, metadata: dict = None):
    """
    Mencatat satu aktivitas user ke collection `activity_logs`.

    Format dokumen mengikuti Chapter 13 Section 3.7:
        {
          "user_id": 1,
          "action": "view_course",
          "target_type": "course",
          "target_id": 5,
          "metadata": {...},
          "timestamp": ISODate(...)
        }
    """
    db = get_mongo_db()
    doc = {
        "user_id": user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "metadata": metadata or {},
        "timestamp": datetime.utcnow(),
    }
    result = db.activity_logs.insert_one(doc)
    return str(result.inserted_id)


def get_popular_courses(limit: int = 5):
    """Aggregation: top course berdasarkan jumlah view_course."""
    db = get_mongo_db()
    pipeline = [
        {"$match": {"action": "view_course"}},
        {"$group": {
            "_id": "$target_id",
            "total_views": {"$sum": 1},
            "unique_users": {"$addToSet": "$user_id"},
        }},
        {"$addFields": {"unique_user_count": {"$size": "$unique_users"}}},
        {"$sort": {"total_views": -1}},
        {"$limit": limit},
        {"$project": {
            "course_id": "$_id",
            "total_views": 1,
            "unique_user_count": 1,
            "_id": 0,
        }},
    ]
    return list(db.activity_logs.aggregate(pipeline))


def get_user_activity_summary(user_id: int):
    """Aggregation: breakdown aktivitas + 10 aktivitas terbaru milik user."""
    db = get_mongo_db()

    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
    ]
    breakdown = list(db.activity_logs.aggregate(pipeline))

    recent = list(
        db.activity_logs.find(
            {"user_id": user_id},
            {"_id": 0, "action": 1, "target_type": 1, "target_id": 1, "timestamp": 1},
        ).sort("timestamp", -1).limit(10)
    )
    for item in recent:
        if "timestamp" in item:
            item["timestamp"] = item["timestamp"].isoformat()

    return {
        "user_id": user_id,
        "actions_breakdown": {item["_id"]: item["count"] for item in breakdown},
        "total_actions": sum(item["count"] for item in breakdown),
        "recent_activities": recent,
    }


def get_daily_activity_summary(days: int = 7):
    """Aggregation: jumlah aksi & user unik per hari, N hari terakhir."""
    db = get_mongo_db()
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "total_actions": {"$sum": 1},
            "unique_users": {"$addToSet": "$user_id"},
        }},
        {"$addFields": {"unique_user_count": {"$size": "$unique_users"}}},
        {"$sort": {"_id": -1}},
        {"$limit": days},
        {"$project": {
            "date": "$_id",
            "total_actions": 1,
            "unique_user_count": 1,
            "_id": 0,
        }},
    ]
    return list(db.activity_logs.aggregate(pipeline))


# ── Learning Analytics ────────────────────────────────────────

def record_learning_progress(user_id: int, course_id: int, enrollment_id: int,
                              progress_percentage: float, completed_content_ids: list):
    """
    Menyimpan/update snapshot progres belajar ke collection `learning_analytics`.
    Satu dokumen per (user_id, course_id) — di-upsert setiap kali progress berubah.
    """
    db = get_mongo_db()
    db.learning_analytics.update_one(
        {"user_id": user_id, "course_id": course_id},
        {
            "$set": {
                "enrollment_id": enrollment_id,
                "progress_percentage": progress_percentage,
                "completed_content_ids": completed_content_ids,
                "last_accessed": datetime.utcnow(),
            }
        },
        upsert=True,
    )


def get_course_completion_stats(course_id: int):
    """Aggregation: rata-rata progres dan jumlah yang sudah 100% pada satu course."""
    db = get_mongo_db()
    pipeline = [
        {"$match": {"course_id": course_id}},
        {"$group": {
            "_id": "$course_id",
            "avg_progress": {"$avg": "$progress_percentage"},
            "total_enrolled": {"$sum": 1},
            "completed_count": {
                "$sum": {"$cond": [{"$gte": ["$progress_percentage", 100]}, 1, 0]}
            },
        }},
        {"$project": {
            "course_id": "$_id",
            "avg_progress": 1,
            "total_enrolled": 1,
            "completed_count": 1,
            "_id": 0,
        }},
    ]
    result = list(db.learning_analytics.aggregate(pipeline))
    return result[0] if result else {
        "course_id": course_id, "avg_progress": 0,
        "total_enrolled": 0, "completed_count": 0,
    }

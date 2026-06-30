"""
Serializer manual (Course -> dict) khusus untuk data yang akan disimpan
ke Redis cache sebagai JSON. Dipisah dari Pydantic Schema (schemas.py)
supaya tidak bergantung pada behaviour from_orm() yang berbeda antar
versi Pydantic/Django Ninja.
"""


def serialize_user(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": user.role,
    }


def serialize_category(category) -> dict | None:
    if category is None:
        return None
    return {
        "id": category.id,
        "name": category.name,
        "parent_id": category.parent_id,
    }


def serialize_course(course) -> dict:
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "price": course.price,
        "image": course.image.url if course.image else "",
        "teacher": serialize_user(course.teacher),
        "category": serialize_category(course.category),
        "created_at": course.created_at.isoformat(),
        "updated_at": course.updated_at.isoformat(),
    }


def serialize_course_detail(course) -> dict:
    data = serialize_course(course)
    data["coursecontent_set"] = [
        {"id": c.id, "name": c.name, "order": c.order}
        for c in course.coursecontent_set.all()
    ]
    return data

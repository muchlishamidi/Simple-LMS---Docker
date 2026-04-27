from ninja import Schema, Field
from datetime import datetime
from typing import Optional, List


class UserOut(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
    role: str


class RegisterIn(Schema):
    username: str
    email: str
    password: str
    first_name: str = ''
    last_name: str = ''
    role: str = 'student'


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    message: str
    user: UserOut


class UpdateProfileIn(Schema):
    first_name: str = ''
    last_name: str = ''
    email: str = ''


class CategoryOut(Schema):
    id: int
    name: str
    parent_id: Optional[int] = None


class CourseIn(Schema):
    name: str
    description: str = '-'
    price: int = 10000


class CoursePatchIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None


class CourseOut(Schema):
    id: int
    name: str
    description: str
    price: int
    image: Optional[str] = ''
    teacher: UserOut
    category: Optional[CategoryOut] = None
    created_at: datetime
    updated_at: datetime


class ContentOut(Schema):
    id: int
    name: str
    order: int


class DetailCourseOut(CourseOut):
    contents: List[ContentOut] = Field(..., alias='coursecontent_set')


class PaginatedCourseOut(Schema):
    total: int
    page: int
    page_size: int
    results: List[CourseOut]


class EnrollmentIn(Schema):
    course_id: int


class EnrollmentOut(Schema):
    id: int
    course_id: int
    roles: str


class MyCourseOut(Schema):
    id: int
    course: CourseOut = Field(..., alias='course_id')
    roles: str


class ProgressIn(Schema):
    content_id: int
    is_completed: bool = True


class ProgressOut(Schema):
    id: int
    is_completed: bool
    completed_at: Optional[datetime] = None
from django.db import models


class CourseQuerySet(models.QuerySet):
    def for_listing(self):
        return (
            self.select_related('teacher', 'category')
            .prefetch_related('coursecontent_set', 'coursemember_set')
            .annotate(
                member_count=models.Count('coursemember', distinct=True),
                content_count=models.Count('coursecontent', distinct=True),
            )
        )


class CourseManager(models.Manager):
    def get_queryset(self):
        return CourseQuerySet(self.model, using=self._db)

    def for_listing(self):
        return self.get_queryset().for_listing()


class CourseMemberQuerySet(models.QuerySet):
    def for_student_dashboard(self, user):
        return (
            self.filter(user_id=user)
            .select_related('course_id', 'course_id__teacher', 'course_id__category')
            .prefetch_related('course_id__coursecontent_set', 'progress')
        )


class CourseMemberManager(models.Manager):
    def get_queryset(self):
        return CourseMemberQuerySet(self.model, using=self._db)

    def for_student_dashboard(self, user):
        return self.get_queryset().for_student_dashboard(user)
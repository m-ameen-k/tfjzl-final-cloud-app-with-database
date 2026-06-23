import logging
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from .models import Course, Enrollment, Question, Choice, Submission

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except Exception:
            logger.error("New user")
        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect("onlinecourse:index")
        context['message'] = "User already exists."
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        context['message'] = "Invalid username or password."
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    is_enrolled = False
    if user.id is not None:
        num_results = Enrollment.objects.filter(user=user, course=course).count()
        if num_results > 0:
            is_enrolled = True
    return is_enrolled


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = self.object
        if self.request.user.is_authenticated:
            course.is_enrolled = check_if_enrolled(self.request.user, course)
        return context


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)
    if not is_enrolled and user.is_authenticated:
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))


def extract_answers(request):
    submitted_answers = []
    for key in request.POST:
        if key.startswith('choice'):
            value = request.POST[key]
            choice_id = int(value)
            submitted_answers.append(choice_id)
    return submitted_answers


def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)
    enrollment = get_object_or_404(Enrollment, user=request.user, course=course)
    submission = Submission.objects.create(enrollment=enrollment)

    selected_choice_ids = extract_answers(request)
    selected_choices = Choice.objects.filter(id__in=selected_choice_ids)
    submission.choices.set(selected_choices)

    return HttpResponseRedirect(
        reverse(
            viewname='onlinecourse:show_exam_result',
            args=(course.id, submission.id)
        )
    )


def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(Submission, pk=submission_id)
    selected_ids = list(submission.choices.values_list('id', flat=True))

    total_score = 0
    total_grade = 0
    question_results = []

    for question in course.question_set.all():
        choices = question.choice_set.all()
        correct_ids = list(choices.filter(is_correct=True).values_list('id', flat=True))
        selected_for_question = [
            choice_id for choice_id in selected_ids
            if choices.filter(id=choice_id).exists()
        ]

        is_correct = set(selected_for_question) == set(correct_ids)

        total_grade += question.grade
        if is_correct:
            total_score += question.grade

        question_results.append({
            'question': question,
            'choices': choices,
            'selected_ids': selected_for_question,
            'correct_ids': correct_ids,
            'is_correct': is_correct,
        })

    grade = round((total_score / total_grade) * 100, 2) if total_grade else 0

    context = {
        'course': course,
        'grade': grade,
        'question_results': question_results,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)

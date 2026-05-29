from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

from userauths.models import User, Profile
from userauths.forms import UserRegisterForm

def RegisterView(request):
    if request.user.is_authenticated:
        messages.warning(request, f'Hey, you already logged in!')
        return redirect("hotel:index")

    form = UserRegisterForm(request.POST or None)
    if form.is_valid():
        form.save()
        full_name = form.cleaned_data.get('full_name')
        phone = form.cleaned_data.get('phone')
        email = form.cleaned_data.get('email')
        password = form.cleaned_data.get('password1')

        user = authenticate(email=email, password=password)
        login(request, user)

        messages.success(request, f'Hey {full_name}, your account has been created successfully!')

        profile = Profile.objects.get(user=request.user)
        profile.full_name = full_name
        profile.phone = phone
        profile.save()

        return redirect("hotel:index")

    context = {
        'form': form
    }
    return render(request, 'userauths/sign-up.html', context)


def LoginView(request):
    if request.user.is_authenticated:
        messages.warning(request, 'You are already logged in!')
        return redirect("hotel:index")

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            # We attempt to retrieve user to be precise in our error message, though authenticate handles email directly in this custom backend approach
            user_obj = User.objects.get(email=email)
            user = authenticate(request, email=email, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, 'You are logged in successfully!')
                return redirect("hotel:index")
            else:
                messages.warning(request, 'Email or password is incorrect!')
        except User.DoesNotExist:
            messages.warning(request, 'User does not exist!')

    return render(request, 'userauths/sign-in.html')


def LogoutView(request):
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect("userauths:sign-in")

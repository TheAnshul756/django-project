from django.shortcuts import render,redirect
from django.http import HttpResponse,Http404,HttpResponseRedirect
from .models import *
from django.shortcuts import get_object_or_404
from instamojo_wrapper import Instamojo
from home import API_KEY,AUTH_TOKEN
from django.urls import reverse
from datetime import datetime
from django.contrib.auth import login, authenticate,logout
from .forms import SignUpForm
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
import re
import MySQLdb
api = Instamojo(api_key=API_KEY, auth_token=AUTH_TOKEN, endpoint='https://test.instamojo.com/api/1.1/')
def conn():
    return MySQLdb.connect("127.0.0.1","root","12345678","rentafolio2" )
def check_email(email):
    try:
        validate_email( email )
        return True
    except ValidationError:
        return False

# Create your views here.
def test(request) :
    return render(request, 'home/issued_books.html')
def index(request):
    return render(request,'home/index.html')

def bookDetailView(request,bid):
    bk=get_object_or_404(Book,id=bid)
    rating=str(int(bk.rating))
    edition=bk.edition.strftime('%B') +" "+str(bk.edition.year)
    context={
        'book':bk,
        'rating':rating,
        'edition':edition,
    }
    return render(request,'home/single_product.html',context=context)
def catalogView(request):
    template_name='home/shop.html'
    books=Book.objects.all()
    status_books=[1 for x in books]
    final_books=[]
    if 'genre' in request.GET:
        genre_filter=request.GET.getlist('genre')
        for idx,i in enumerate(books):
            if i.genre.name not in genre_filter:
                status_books[idx]=0
    
    if 'price' in request.GET:
        price=int(request.GET['price'])
        for idx,i in enumerate(books):
            if i.mrp > price:
                status_books[idx]=0
    
    if 'rating' in request.GET:
        rating=float(request.GET['rating'])
        for idx,i in enumerate(books):
            if i.rating < rating:
                status_books[idx]=0
               
    if 'book_name' in request.GET:
        book_name=request.GET['book_name']
        reg=r"^.*"+book_name+".*$"
        for idx,i in enumerate(books):
            if not re.search(reg,i.title,re.IGNORECASE):
                status_books[idx]=0

    for idx,i in enumerate(books):
        if(status_books[idx]==1):
            final_books.append({
                'book':i,
                'rating':str(int(i.rating)),
            })
    genres=Genre.objects.all()

    return render(request,template_name,context={'books':final_books,'genres':genres,})

@login_required
@csrf_exempt
def paymentView(request):
    template_name='home/checkout.html'
    if 'book_id' not in request.GET:
        raise Http404
    temp=int(request.GET['book_id'])
    # print("YO")
    bid=get_object_or_404(Book,id=temp)
    bk_instances=bid.bookinstance_set.all().filter(status=1,active=True)
    # print("YESS")
    try:
        a=bk_instances[0]
    except:
        raise Http404
    request.session['instance_id']=a.id
    # request.session['instance_id']=a
    context={
        'book':bid,
        'balance':request.user.profile.balance,
    }
    if request.method=="POST":
        topay=bid.mrp
        balance=request.user.profile.balance
        if 'balused' in request.POST:
            print("HI")
            if(balance>bid.mrp):
                topay=0
            else:            
                topay-=balance
                print(topay)
                usr=request.user.profile
                usr.balance=0
                usr.save()
        if(topay>0):
            if(topay<10):
                topay=10
            response = api.payment_request_create(
                        amount=str(topay),
                        purpose="Rentafolio Book Rental",
                        send_email=False,
                        email=request.user.email,
                        buyer_name=request.user.username,
                        phone=request.user.profile.contact,
                        redirect_url=request.build_absolute_uri(reverse("checkout")),
                    )
                    
            return HttpResponseRedirect(response['payment_request']['longurl'])
        else:
            usr=request.user.profile
            usr.balance-=bid.mrp
            usr.save()
            request.session["book_purchased"]=True
            # return HttpResponseRedirect(reverse('checkout'))
            insta_id=request.session['instance_id']
            i=get_object_or_404(BookInstance,id=insta_id)
            i.borrower=request.user.profile
            i.b_date=datetime.now()
            i.status=0
            i.save()
            del request.session['instance_id']
            return HttpResponseRedirect(reverse('checkout'))
    return render(request,template_name,context=context)

        
@login_required
def profileView(request):
    usr=request.user
    context={
        'user':usr,
        'issued_books':len(usr.profile.borrowed.filter(status=0,active=1)),
        'uploaded_books':len(usr.profile.uploaded.all())
    }
    template_name='home/profile.html'
    if request.method=="POST":
        first_name=request.POST['first_name']
        last_name=request.POST['last_name']
        contact=request.POST['contact']
        if not (len(contact)==10 and contact.isdigit()):
            messages.warning(request,"Contact number invalid",context=context)
            return render(request,template_name)
        usr.first_name=first_name
        usr.last_name=last_name
        usr.save()
        prof=request.user.profile
        prof.contact=contact
        prof.save()
        context['updated']="Details Successfully updated"
        return render(request,template_name,context=context)
    return render(request, template_name,context=context)

@login_required
def issuedView(request):
    template_name='home/issued_books.html'
    if request.method=="POST":
        return_id=int(request.POST['return_id'])
        return_book=BookInstance.objects.get(id=return_id)
        return_book.borrower=None
        return_book.status=1
        return_book.save()
        days_issued=(datetime.now().date()-return_book.b_date.date()).days
        return_pct=0
        credit_pct=0
        if(days_issued<=30):
            return_pct=0.8
            credit_pct=0.1
        elif(days_issued<=60):
            return_pct=0.7
            credit_pct=0.15
        elif(days_issued<=180):
            credit_pct=0.25
            return_pct=0.5
        elif(days_issued<=360):
            return_pct=0.4
            credit_pct=0.3
        else:
            return_pct=0
            credit_pct=0.8
        usr=request.user.profile
        uploader=return_book.uploader
        usr.balance+=return_book.book.mrp*return_pct
        usr.save()
        uploader.balance+=credit_pct*return_book.book.mrp
        uploader.save()
        # db=conn()
        # query="update bookinstance set borrower_id=NULL,status=1 where instance_id={};".format(return_book.id)
        # cursor.execute(query)
        # db.commit()
        # db.close()
        messages.warning(request,"Book successfully returned")
        return HttpResponse("OK")
    books=request.user.profile.borrowed.filter(status=0,active=True)
    # print(len(books))
    return render(request,template_name='home/issued_books.html',context={'books':books,})
    if len(issued_books)==0:
        return HttpResponse("You dont have any books issued")
    else:
        for i in issued_books:
            p+="<p>"+i.book.title+" issued on "+str(i.b_date.strftime("%-d %B, %Y"))+"</p>"
        return HttpResponse(p)


def signup(request):
    template_name='home/signup.html'
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('index'))
    if request.method == 'POST':
        post = request.POST
        email = post.get('email')
        email = email.lower()
        if not check_email(email):
            messages.warning(request,"Email is not valid")
            return render(request,template_name)
        username = post.get('username')
        if username == "":
            messages.warning(request, "Enter a valid email address and username.", fail_silently=True)
            return render(request,template_name)

        if len(email) > 40 or len(email) <= 0:
            messages.warning(request, "Email address is too long. Register with a different email address.", fail_silently=True)
            return render(request,template_name)
        # print("reched here")
        password1 = post.get('password1')
        password2 = post.get('password2')
        if password1 != password2:
            messages.warning(request, "Passwords did not match.", fail_silently=True)
            return render(request,template_name)
        if len(password1) < 5:
            messages.warning(request, "Enter a password having atleast 5 characters.", fail_silently=True)
            return render(request,template_name)
        # print("reached here")
        try:
            already_a_user = User.objects.get(username=username)
            messages.warning(request,"Username already exists")
            return render(request,template_name)
        except:#unique user.
            already_a_user = False
        # print("reached here")        
        try:
            first_name=post.get('first_name')
            last_name=post.get('last_name')
            contact=post.get('contact')
            if first_name=="" or last_name=="" or contact=="":
                messages.warning(request,"Fields cannot be empty")
                return render(request,template_name) 
            if not (len(contact)==10 and contact.isdigit()):
                messages.warning(request,"Contact number invalid")
                return render(request,template_name)
            
            user = User.objects.create_user(username=username,email=email)
            # print("reached here")

            user.set_password(password1)
            user.is_active=True
            user.save()
            user.refresh_from_db()
            # print("reached here")

            user.profile.contact=contact
            # user.profile.address=address
            user.first_name=first_name
            user.last_name=last_name
            user.save()
            # db = conn()
            # cursor = db.cursor()
            # query="insert into user values({},0,'{}');".format(user.id,contact)
            # cursor.execute(query)
            # db.commit()
            # db.close()
            return redirect(reverse('login'))
        except:
            messages.warning(request,"Fields not filled properly")
            user.delete()
            return render(request,template_name)
    return render(request, template_name)

def user_login(request):
    template_name='home/login.html'
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse('index'))
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user:
            if user.is_active:
                login(request,user)
                return HttpResponseRedirect(reverse('index'))
            else:
                return HttpResponse("Your account was inactive.")
        else:
            messages.warning(request,"Invalid Login Credentials")
            return render(request,template_name)
    else:
        return render(request, template_name)

@login_required
def user_logout(request):
    logout(request)
    return HttpResponseRedirect(reverse('index'))

@login_required
def checkout(request):
    template_name='home/thanks.html'
    if request.session.get('book_purchased',False):
        return render(request,template_name)
    if 'payment_request_id' in request.GET and 'payment_id' in request.GET:
        try:
            payment_request_id=request.GET['payment_request_id']
            payment_id=request.GET['payment_id']
            response = api.payment_request_payment_status(payment_request_id, payment_id)
            pstatus=response['payment_request']['payment']['status']
            if(pstatus=="Failed"):
                return HttpResponse("Your Payment failed. Please go to the register page and try again")
            if(pstatus=="Credit"):
                instance_id=request.session.get('instance_id',-1)
                bk=get_object_or_404(BookInstance,id=instance_id)
                bk.status=0
                bk.borrower=request.user.profile
                bk.b_date=datetime.now()
                bk.save()
                # db=conn()
                # cursor=db.cursor()
                # query="update bookinstance set status=0,b_date=NOW(),borrower_id={} where instance_id={}".format(request.user.profile.id,instance_id)
                # cursor.execute(query)
                # db.commit()
                # db.close()
                del request.session['instance_id']
                return render(request,template_name)
        except:
            raise Http404
        raise Http404
    raise Http404

@login_required
def uploadedView(request):
    template_name='home/uploaded_books.html'
    uploaded_books=request.user.profile.uploaded.all()
    return render(request,template_name,context={
        'books':uploaded_books,
    })

@login_required
def addBookView(request):
    template_name='home/add_book.html'
    books=Book.objects.all()
    if request.method=="POST":
        book_id=request.POST["book_id"]
        bk=BookInstance(book=book_id,uploader=request.user.profile)
        bk.save()
        # db=conn()
        # query="insert into bookinstance values({},{},NOW(),0,0,NULL,{}".format(bk.id,book_id,request.user.profile.id)
        # cursor.execute(query)
        # db.commit()
        # db.close()
        context={
            'books':books,
            'success':"Book successfully added",
        }
        return render(request,template_name,context=context)
    return render(request,template_name,context={'books':books,})
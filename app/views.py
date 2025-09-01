# core/views.py
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import render, redirect, get_object_or_404
import requests
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import json
from django.contrib.auth.hashers import make_password, check_password
import logging
from django.utils import timezone
from functools import wraps
import razorpay
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Count, Sum # NEW: Import Count and Sum for aggregations



from .models import Member, Librarian, Book, Borrowing

logger = logging.getLogger(__name__)


RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET = settings.RAZORPAY_KEY_SECRET
client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# --- Custom Decorators for User Type Checking ---
def member_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('user_id'): # Check if user_id is in session (implies logged in)
            messages.error(request, "Please log in to access this page.")
            return redirect('login')
        
        if request.session.get('user_type') == 'member':
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "Access denied. Only members can access this page.")
            return redirect('home')
    return _wrapped_view

def librarian_required(view_func):
    """
    Decorator for views that checks if the user is logged in as a librarian.
    If not, redirects to the login page or displays an access denied message.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.session.get('user_id'): # Check if user_id is in session (implies logged in)
            messages.error(request, "Please log in to access this page.")
            return redirect('login')
        
        if request.session.get('user_type') == 'librarian':
            return view_func(request, *args, **kwargs)
        else:
            messages.error(request, "Access denied. Only librarians can access this page.")
            return redirect('home')
    return _wrapped_view

# In app/views.py

# ... (make sure 'requests' and 'cache' are imported at the top of the file)
# from django.core.cache import cache
# import requests

# In app/views.py
# In app/views.py

# ... (make sure 'requests' and 'cache' are imported at the top of the file)
# from django.core.cache import cache
# import requests

def home(request):
    trending_books_cache_key = "trending_books_carousel_v3" # New key to force a refresh
    trending_books = cache.get(trending_books_cache_key)

    if not trending_books:
        trending_books = []
        queries = ["new york times bestseller", "fiction", "fantasy", "non-fiction"]
        google_books_api_url = "https://www.googleapis.com/books/v1/volumes"
        
        try:
            for query in queries:
                if len(trending_books) >= 12:
                    break
                params = {
                    'q': query,
                    'orderBy': 'relevance',
                    'maxResults': 5, # Fetch a bit more to account for missing images
                    'printType': 'books',
                    'filter': 'paid-ebooks',
                    'fields': 'items(id,volumeInfo(title,imageLinks))'
                }
                response = requests.get(google_books_api_url, params=params)
                response.raise_for_status()
                data = response.json().get('items', [])
                
                for item in data:
                    volume_info = item.get('volumeInfo', {})
                    image_links = volume_info.get('imageLinks', {})
                    
                    # --- THIS IS THE ROBUST FIX ---
                    
                    # 1. Define a reliable placeholder
                    placeholder_url = "https://placehold.co/220x330/121826/a9b3c9?text=Cover+Not+Available"
                    
                    # 2. Get the best available URL, or use the placeholder if none exist
                    thumbnail_url = image_links.get('large') or \
                                    image_links.get('medium') or \
                                    image_links.get('small') or \
                                    image_links.get('thumbnail') or \
                                    placeholder_url
                    
                    # 3. Ensure the URL is HTTPS
                    if thumbnail_url.startswith('http://'):
                        thumbnail_url = thumbnail_url.replace('http://', 'https://', 1)

                    # 4. Attempt to upgrade quality if it's a standard thumbnail
                    if "zoom=1" in thumbnail_url:
                        thumbnail_url = thumbnail_url.replace("zoom=1", "zoom=0")

                    book_data = {
                        'id': item.get('id'),
                        'thumbnail': thumbnail_url,
                        'title': volume_info.get('title', 'No Title')
                    }
                    
                    if book_data['id'] and book_data['id'] not in [b['id'] for b in trending_books]:
                        trending_books.append(book_data)

            cache.set(trending_books_cache_key, trending_books, 60 * 60 * 24)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Could not fetch trending books for homepage: {e}")
            trending_books = []

    context = {
        'trending_books': trending_books
    }
    return render(request, 'index.html', context)

def register_member(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        phone_number = request.POST.get('phone_number')
        user_type = request.POST.get('user_type') # This expects 'member' from the form

        # Check if email is already registered as a Member
        if Member.objects.filter(email=email).exists():
            messages.error(request, 'This email is already registered as a Member.')
            return render(request, 'register.html')
        
        # Check if email is already registered as a Librarian
        if Librarian.objects.filter(email=email).exists():
            messages.error(request, 'This email is already registered as a Librarian.')
            return render(request, 'register.html')
        
        if password != confirm_password:
            messages.error(request,'Passwords do not match, please try again.')
            return render(request,'register.html')
        
        if user_type == 'member':
            try:
                hashed_password = make_password(password)
                Member.objects.create(
                    name=name,
                    email=email,
                    password=hashed_password,
                    phone_number=phone_number
                )
                
                messages.success(request,'Account Created Successfully! Please Log In.')
                return redirect('login')
            except Exception as e:
                messages.error(request, f'An error occurred during registration: {e}')
                return render(request, 'register.html')
        else:
            messages.error(request, 'Invalid user type for registration.')
            return render(request, 'register.html')
    return render(request, 'register.html')

# In app/views.py

def login_view(request):
    # Handle POST requests (when the user submits the form)
    if request.method == 'POST':
        email = request.POST.get('username')
        password = request.POST.get('password')
        next_url = request.GET.get('next') or request.POST.get('next')
        
        user_obj = None
        authenticated_user_type = None

        # Try to authenticate as a Member
        try:
            member = Member.objects.get(email=email)
            if check_password(password, member.password):
                if not member.is_active:
                    messages.error(request, 'This account has been deactivated. Please contact the library.')
                    # On failure, re-render the form, passing the email back
                    return render(request, 'login.html', {'username': email, 'next': next_url})
                else:
                    user_obj = member
                    authenticated_user_type = 'member'
        except Member.DoesNotExist:
            pass  # Continue to check for a librarian

        # If not authenticated as member, try as Librarian
        if not user_obj:
            try:
                librarian = Librarian.objects.get(email=email)
                if check_password(password, librarian.password):
                    user_obj = librarian
                    authenticated_user_type = 'librarian'
            except Librarian.DoesNotExist:
                pass  # Neither member nor librarian found

        # If authentication was successful
        if user_obj and authenticated_user_type:
            request.session.flush()
            request.session['user_id'] = user_obj.id
            request.session['user_type'] = authenticated_user_type
            request.session.save()

            if authenticated_user_type == 'member':
                messages.success(request, f'Welcome back, {user_obj.name}!')
                redirect_target = next_url if next_url else 'userpage'
            else:  # 'librarian'
                messages.success(request, 'Welcome, Librarian!')
                redirect_target = next_url if next_url else 'librarian_dashboard'
            
            return redirect(redirect_target)

        # If authentication failed for any reason (wrong password, user not found)
        messages.error(request, 'Invalid email or password.')
        return render(request, 'login.html', {'username': email, 'next': next_url})

    # Handle GET requests (when the user first visits the login page)
    else:
        context = {
            'next': request.GET.get('next')
        }
        return render(request, 'login.html', context)

def browse_books(request):
    query = request.GET.get('q', '.')
    page_number = request.GET.get('page', 1)
    books_per_page = 24
    try:
        current_page = int(page_number)
        max_api_start_index = 1000
        
        start_index = (current_page - 1) * books_per_page
        
        if start_index > max_api_start_index:
            start_index = max_api_start_index
            current_page = (max_api_start_index // books_per_page) + 1
    except ValueError:
        current_page = 1
        start_index = 0

    books_data = []
    effective_total_items = 0
    google_books_api_url = "https://www.googleapis.com/books/v1/volumes"
    cache_key = f"books_api_cache_{query}_{current_page}"
    cached_data = cache.get(cache_key)

    if cached_data:
        logger.info(f"Serving books from cache for query: {query}, page: {current_page}")
        books_data = cached_data['books']
        effective_total_items = cached_data['effective_total_items']
    else:
        logger.info(f"Fetching books from Google Books API for query: {query}, page: {query}")
        params = {
            'q': query,
            'startIndex': start_index,
            'maxResults': books_per_page,
            'fields': 'totalItems,items(id,volumeInfo(title,authors,description,imageLinks,infoLink))'
        }
        try:
            response = requests.get(google_books_api_url, params=params)
            response.raise_for_status()
            data = response.json()
            api_total_items = data.get('totalItems', 0)
            
            effective_total_items = min(api_total_items, max_api_start_index + books_per_page)
            items = data.get('items', [])
            for item in items:
                volume_info = item.get('volumeInfo', {})
                title = volume_info.get('title', 'No Title Available')
                authors = volume_info.get('authors', [])
                description = volume_info.get('description', 'No description available.')
                image_links = volume_info.get('imageLinks', {})
                image_url = image_links.get('thumbnail') or image_links.get('smallThumbnail') or 'https://placehold.co/600x400/cccccc/333333?text=No+Cover'
                info_link = volume_info.get('infoLink', '#')
                books_data.append({
                    'id': item.get('id'), # Google Books ID
                    'title': title,
                    'authors': authors,
                    'description': description,
                    'image_url': image_url,
                    'info_link': info_link,
                })
            cache.set(cache_key, {'books': books_data, 'effective_total_items': effective_total_items})
        except requests.exceptions.HTTPError as e:
            error_message = f"Error fetching books: {e.response.status_code} - {e.response.reason}"
            if e.response.status_code == 400:
                error_message = "Could not fetch books for this page. The requested page might be too far or invalid."
            logger.error(f"HTTP Error fetching books from Google Books API: {e}")
            books_data = []
            effective_total_items = 0
            messages.error(request, error_message)
        except requests.exceptions.RequestException as e:
            logger.error(f"General Request Error fetching books from Google Books API: {e}")
            books_data = []
            effective_total_items = 0
            messages.error(request, "A network error occurred while fetching books. Please try again.")

    paginator = Paginator(range(effective_total_items), books_per_page)
   
    if current_page > paginator.num_pages:
        current_page = paginator.num_pages if paginator.num_pages > 0 else 1
    try:
        page_obj = paginator.page(current_page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    page_range = []
    num_pages = paginator.num_pages
    current_page_num = page_obj.number
   
    pages_to_show_around = 2
    if num_pages <= (2 * pages_to_show_around + 1 + 2):
        page_range = paginator.page_range
    else:
        page_range.append(1)
        if current_page_num > (pages_to_show_around + 2):
            page_range.append('...')
        for i in range(max(2, current_page_num - pages_to_show_around),
                       min(num_pages, current_page_num + pages_to_show_around) + 1):
            page_range.append(i)
        if current_page_num < (num_pages - pages_to_show_around - 1):
            if '...' not in page_range[-1:]:
                page_range.append('...')
            if num_pages not in page_range:
                page_range.append(num_pages)
        elif num_pages not in page_range and num_pages > 1:
            page_range.append(num_pages)

    context = {
        'books': books_data,
        'page_title': f"Browse Books for '{query}'",
        'query': query,
        'paginator': paginator,
        'page_obj': page_obj,
        'page_range_display': page_range,
    }
    return render(request, 'browse_books.html', context)

def book_detail(request, google_books_id):
    book_details = None
    cache_key = f"single_book_detail_{google_books_id}"
    book_details = cache.get(cache_key)

    if not book_details:
        google_books_api_url = f"https://www.googleapis.com/books/v1/volumes/{google_books_id}"
        try:
            response = requests.get(google_books_api_url)
            response.raise_for_status()
            data = response.json()
            volume_info = data.get('volumeInfo', {})
            book_details = {
                'id': data.get('id'),
                'title': volume_info.get('title', 'No Title Available'),
                'authors': volume_info.get('authors', []),
                'description': volume_info.get('description', 'No description available.'),
                'image_url': volume_info.get('imageLinks', {}).get('thumbnail') or volume_info.get('imageLinks', {}).get('smallThumbnail') or 'https://placehold.co/600x400/cccccc/333333?text=No+Cover',
                'info_link': volume_info.get('infoLink', '#'),
                'published_date': volume_info.get('publishedDate', 'N/A'),
                'page_count': volume_info.get('pageCount', 'N/A'),
                'categories': volume_info.get('categories', []),
                'publisher': volume_info.get('publisher', 'N/A'),
            }
            cache.set(cache_key, book_details, timeout=3600) # Cache for 1 hour
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching single book details for {google_books_id}: {e}")
            messages.error(request, "Could not fetch book details. Please try again.")
            return redirect('browse_books')
    
    current_member = None
    existing_request_or_payment_pending = False
    book_obj_id = None # Initialize to None

    # Only execute member-specific logic if a user is logged in
    if request.session.get('user_id') and request.session.get('user_type') == 'member':
        member_id = request.session.get('user_id')
        try:
            current_member = Member.objects.get(id=member_id)
            
            # Get or create the Book object in your database
            book_obj, created = Book.objects.get_or_create(
                google_books_id=book_details['id'],
                defaults={
                    'title': book_details['title'],
                    'author': ", ".join(book_details['authors']) if book_details['authors'] else '',
                    'image_url': book_details['image_url'],
                    'description': book_details['description'],
                    'info_link': book_details['info_link'],
                    'copies_available': 1, # Default to 1 if new book, librarians can adjust stock
                    'total_copies': 1,
                }
            )
            book_obj_id = book_obj.id # Store the ID for context

            # Check if the member already has a pending or payment_pending request for this book
            existing_request_or_payment_pending = Borrowing.objects.filter(
                member=current_member,
                book=book_obj,
                status__in=['pending_purchase', 'payment_pending']
            ).exists()

            # Handle POST request for "Request to Buy" (only if member is logged in)
            if request.method == 'POST':
                if existing_request_or_payment_pending:
                    messages.warning(request, f"You already have a pending or payment-pending request for '{book_obj.title}'.")
                    return redirect('userpage') # Redirect to userpage to show existing request

                # Create a new purchase request with status 'pending_purchase'
                Borrowing.objects.create(
                    member=current_member,
                    book=book_obj,
                    request_date=timezone.now(),
                    status='pending_purchase'
                )
                messages.success(request, f"Your request to purchase '{book_obj.title}' has been submitted for librarian approval!")
                
                # Send email notification to librarians for new purchase request
                librarians = Librarian.objects.all()
                if librarians.exists():
                    subject = f"New BookHub Purchase Request: '{book_obj.title}'"
                    message = (
                        f"Dear Librarian,\n\n"
                        f"A new purchase request has been submitted by {current_member.name} ({current_member.email}).\n\n"
                        f"Book: {book_obj.title} by {book_obj.author}\n"
                        f"Requested on: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"Please review this request in your Librarian Dashboard.\n\n"
                        f"BookHub Team"
                    )
                    recipient_list = [lib.email for lib in librarians]
                    try:
                        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, recipient_list, fail_silently=False)
                        logger.info(f"Email sent to librarians about new request for {book_obj.title}")
                    except Exception as e:
                        logger.error(f"Failed to send email to librarians about new request: {e}")
                return redirect('userpage') # Redirect to userpage after successful request
                
        except Member.DoesNotExist:
            # This handles cases where a user_id is in session but the member object doesn't exist
            messages.error(request, "Your member profile could not be found. Please log in again.")
            return redirect('logout') # Force logout to clear invalid session
    
    context = {
        'book': book_details,
        'member': current_member, # Will be None if not logged in, which is handled in the template
        'page_title': f"Book Details: {book_details['title']}",
        'existing_request_or_payment_pending': existing_request_or_payment_pending,
        'book_db_id': book_obj_id # Pass the DB ID of the book if available
    }
    return render(request, 'book_detail.html', context)

# MODIFIED: buy_request_view now just redirects to book_detail
@member_required
def buy_request_view(request, google_books_id):
    # This view is now largely redundant as its logic is in book_detail
    # It will simply redirect to the book_detail page
    messages.info(request, "Please view book details before making a purchase request.")
    return redirect('book_detail', google_books_id=google_books_id)


def logout_view(request):
    if 'user_id' in request.session:
        del request.session['user_id']
    if 'user_type' in request.session:
        del request.session['user_type']
    request.session.clear()
    request.session.cycle_key()
    messages.info(request, "You have been logged out.")
    return redirect('login')

@member_required
def userpage(request):
    member_id = request.session.get('user_id')
    user_type = request.session.get('user_type')

    if user_type != 'member' or not member_id:
        messages.error(request, "Access denied. Please log in as a member.")
        return redirect('login')
    try:
        current_member = Member.objects.get(id=member_id)
    except Member.DoesNotExist:
        messages.error(request, "Your member profile could not be found.")
        if 'user_id' in request.session:
            del request.session['user_id']
        if 'user_type' in request.session:
            del request.session['user_type']
        request.session.clear()
        request.session.cycle_key()
        return redirect('login')

    # Fetch pending buy requests (still awaiting librarian approval)
    pending_requests_qs = Borrowing.objects.filter(member=current_member, status='pending_purchase').select_related('book').order_by('-request_date')
    pending_requests = []
    for req in pending_requests_qs:
        pending_requests.append({
            'title': req.book.title,
            'author': req.book.author,
            'request_date': req.request_date.strftime('%Y-%m-%d %H:%M'),
            'cover': req.book.image_url,
            'transaction_id': req.id,
            'status': req.status,
        })
    
    # Fetch payment pending requests (approved by librarian, awaiting member payment)
    payment_pending_requests_qs = Borrowing.objects.filter(member=current_member, status='payment_pending').select_related('book').order_by('-approval_date')
    payment_pending_requests = []
    for req in payment_pending_requests_qs:
        payment_pending_requests.append({
            'title': req.book.title,
            'author': req.book.author,
            'approval_date': req.approval_date.strftime('%Y-%m-%d %H:%M') if req.approval_date else 'N/A',
            'cover': req.book.image_url,
            'transaction_id': req.id,
            'razorpay_order_id': req.razorpay_order_id,
            'amount_display': req.amount / 100, # Divide by 100 here for display in rupees
            'status': req.status,
        })

    # Fetch purchased books (completed payments)
    purchased_books_qs = Borrowing.objects.filter(member=current_member, status='purchased').select_related('book').order_by('-approval_date')
    purchased_books = []
    for purchase_record in purchased_books_qs:
        purchased_books.append({
            'title': purchase_record.book.title,
            'author': purchase_record.book.author,
            'purchase_date': purchase_record.approval_date.strftime('%Y-%m-%d') if purchase_record.approval_date else 'N/A',
            'cover': purchase_record.book.image_url,
            'transaction_id': purchase_record.id,
            'status': purchase_record.status,
        })

    # Fetch rejected or failed payments
    rejected_or_failed_qs = Borrowing.objects.filter(member=current_member, status__in=['rejected_purchase', 'payment_failed']).select_related('book').order_by('-approval_date')
    rejected_or_failed = []
    for item in rejected_or_failed_qs:
        # Pre-process status for display to remove "_purchase" and "_failed"
        display_status = item.status.replace('_purchase', '').replace('_failed', '').title()
        rejected_or_failed.append({
            'title': item.book.title,
            'author': item.book.author,
            'date': item.approval_date.strftime('%Y-%m-%d %H:%M') if item.approval_date else item.request_date.strftime('%Y-%m-%d %H:%M'),
            'status': item.status, # Keep original status for conditional class
            'display_status': display_status, # New field for display
            'cover': item.book.image_url,
        })


    context = {
        'member': current_member,
        'pending_requests': pending_requests,
        'payment_pending_requests': payment_pending_requests,
        'purchased_books': purchased_books,
        'rejected_or_failed_transactions': rejected_or_failed,
        'page_title': f"Welcome, {current_member.name}!",
        'now': timezone.now(),
    }
    return render(request, 'userpage.html', context)

# NEW: Member Profile Edit View
@member_required
def member_profile_edit(request):
    member_id = request.session.get('user_id')
    current_member = get_object_or_404(Member, id=member_id)

    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # Validate email uniqueness if changed
        if email and email != current_member.email:
            if Member.objects.filter(email=email).exists():
                messages.error(request, 'This email is already taken by another member.')
                return render(request, 'member_profile_edit.html', {'member': current_member, 'page_title': 'Edit Profile'})
            
            # Also check if it's taken by a librarian
            if Librarian.objects.filter(email=email).exists():
                messages.error(request, 'This email is already taken by a librarian.')
                return render(request, 'member_profile_edit.html', {'member': current_member, 'page_title': 'Edit Profile'})

        # Update fields
        current_member.name = name if name else current_member.name
        current_member.email = email if email else current_member.email
        current_member.phone_number = phone_number if phone_number else current_member.phone_number

        # Handle password change
        if password:
            if password != confirm_password:
                messages.error(request, 'New password and confirm password do not match.')
                return render(request, 'member_profile_edit.html', {'member': current_member, 'page_title': 'Edit Profile'})
            current_member.password = make_password(password) # Hash the new password
        
        try:
            current_member.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('userpage') # Redirect to userpage after successful update
        except Exception as e:
            messages.error(request, f'An error occurred while updating your profile: {e}')
            # Re-render the form with current data and error
            return render(request, 'member_profile_edit.html', {'member': current_member, 'page_title': 'Edit Profile'})

    context = {
        'member': current_member,
        'page_title': 'Edit Profile',
    }
    return render(request, 'member_profile_edit.html', context)



# NEW: View for Librarian Add/Edit Book
@librarian_required
def librarian_add_book(request):
    page_title = "Add New Book"
    if request.method == 'POST':
        google_books_id = request.POST.get('google_books_id')
        title = request.POST.get('title')
        # ... (get other form fields)
        
        # Check for uniqueness
        if google_books_id and Book.objects.filter(google_books_id=google_books_id).exists():
            messages.error(request, f"A book with Google Books ID '{google_books_id}' already exists.")
            return render(request, 'librarian_add_edit_book.html', {'page_title': page_title, 'form_data': request.POST})
        
        try:
            Book.objects.create(
                google_books_id=google_books_id,
                title=title,
                author=request.POST.get('author'),
                description=request.POST.get('description'),
                image_url=request.POST.get('image_url'),
                info_link=request.POST.get('info_link'),
                total_copies=int(request.POST.get('total_copies', 0)),
                copies_available=int(request.POST.get('copies_available', 0))
            )
            messages.success(request, f"New book '{title}' added successfully!")
            return redirect('librarian_book_management')
        except Exception as e:
            messages.error(request, f"Error adding book: {e}")
            return render(request, 'librarian_add_edit_book.html', {'page_title': page_title, 'form_data': request.POST})

    # This handles the GET request
    return render(request, 'librarian_add_edit_book.html', {'page_title': page_title})

@librarian_required
def librarian_edit_book(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    page_title = f"Edit Book: {book.title}"

    if request.method == 'POST':
        google_books_id = request.POST.get('google_books_id')
        
        # Check for uniqueness if the ID was changed
        if google_books_id and google_books_id != book.google_books_id and Book.objects.filter(google_books_id=google_books_id).exists():
            messages.error(request, f"A book with Google Books ID '{google_books_id}' already exists.")
            return render(request, 'librarian_add_edit_book.html', {'book': book, 'page_title': page_title})

        book.google_books_id = google_books_id
        book.title = request.POST.get('title')
        book.author = request.POST.get('author')
        # ... (update other fields)
        book.total_copies = int(request.POST.get('total_copies', 0))
        book.copies_available = int(request.POST.get('copies_available', 0))
        
        try:
            book.save()
            messages.success(request, f"Book '{book.title}' updated successfully!")
            return redirect('librarian_book_management')
        except Exception as e:
            messages.error(request, f"Error updating book: {e}")
            return render(request, 'librarian_add_edit_book.html', {'book': book, 'page_title': page_title})

    # This handles the GET request
    context = {'book': book, 'page_title': page_title}
    return render(request, 'librarian_add_edit_book.html', context)
    

@librarian_required
def librarian_dashboard(request):
    # Filter for pending purchase requests (member initiated, awaiting librarian approval)
    pending_buy_requests = Borrowing.objects.filter(status='pending_purchase').select_related('member', 'book').order_by('request_date')

    # Filter for payment pending requests (librarian approved, awaiting member payment)
    payment_pending_transactions = []
    payment_pending_qs = Borrowing.objects.filter(status='payment_pending').select_related('member', 'book').order_by('approval_date')
    for transaction in payment_pending_qs:
        payment_pending_transactions.append({
            'id': transaction.id,
            'book_title': transaction.book.title,
            'book_author': transaction.book.author,
            'member_name': transaction.member.name,
            'member_email': transaction.member.email,
            'request_date': transaction.request_date,
            'approval_date': transaction.approval_date,
            'razorpay_order_id': transaction.razorpay_order_id,
            'amount_display': transaction.amount / 100, # Convert to rupees for display
            'status': transaction.status,
            'status_display': transaction.get_status_display() # <-- ADD THIS LINE
        })

    # Filter for completed purchases (member paid)
    confirmed_purchases = []
    confirmed_purchases_qs = Borrowing.objects.filter(status='purchased').select_related('member', 'book').order_by('-approval_date')
    for purchase in confirmed_purchases_qs:
        confirmed_purchases.append({
            'id': purchase.id,
            'book_title': purchase.book.title,
            'book_author': purchase.book.author,
            'member_name': purchase.member.name,
            'member_email': purchase.member.email,
            'approval_date': purchase.approval_date,
            'razorpay_payment_id': purchase.razorpay_payment_id,
            'amount_display': purchase.amount / 100, # Convert to rupees for display
            'status': purchase.status,
            'status_display': purchase.get_status_display() # <-- ADD THIS LINE
        })


    # Filter for rejected or failed payments
    rejected_transactions = []
    rejected_qs = Borrowing.objects.filter(status__in=['rejected_purchase', 'payment_failed']).select_related('member', 'book').order_by('-approval_date')
    for transaction in rejected_qs:
        rejected_transactions.append({
            'id': transaction.id,
            'book_title': transaction.book.title,
            'book_author': transaction.book.author,
            'member_name': transaction.member.name,
            'request_date': transaction.request_date,
            'approval_date': transaction.approval_date,
            'status': transaction.status,
            'status_display': transaction.get_status_display() # <-- ADD THIS LINE
        })


    context = {
        'pending_buy_requests': pending_buy_requests,
        'payment_pending_transactions': payment_pending_transactions,
        'confirmed_purchases': confirmed_purchases,
        'rejected_transactions': rejected_transactions,
        'page_title': "Librarian Dashboard",
        'now': timezone.now(),
        }
    return render(request, 'librarian_dashboard.html', context)




@member_required
def initiate_payment_page(request, transaction_id):
    transaction = get_object_or_404(Borrowing, id=transaction_id, member=request.session.get('user_id'), status='payment_pending')
    member = get_object_or_404(Member, id=request.session.get('user_id'))

    context = {
        'transaction_id': transaction.id,
        'razorpay_order_id': transaction.razorpay_order_id,
        'amount': transaction.amount, # Amount in paise (Razorpay expects this)
        'amount_display': transaction.amount / 100, # Amount in rupees for display
        'book_title': transaction.book.title,
        'member_name': member.name,
        'member_email': member.email,
        'member_phone': member.phone_number,
        'RAZORPAY_KEY_ID': RAZORPAY_KEY_ID,
        'page_title': f"Complete Payment for {transaction.book.title}",
    }
    return render(request, 'payment_page.html', context)

@librarian_required
def librarian_book_management(request):
    books = Book.objects.all().order_by('title')
    context = {
        'books': books,
        'page_title': 'Manage Books',
    }
    return render(request, 'librarian_book_management.html', context)

@librarian_required
def librarian_add_edit_book(request, book_id=None):
    book = None
    if book_id:
        book = get_object_or_404(Book, id=book_id)
        page_title = f"Edit Book: {book.title}"
    else:
        page_title = "Add New Book"

    if request.method == 'POST':
        google_books_id = request.POST.get('google_books_id')
        title = request.POST.get('title')
        author = request.POST.get('author')
        description = request.POST.get('description')
        image_url = request.POST.get('image_url')
        info_link = request.POST.get('info_link')
        total_copies = request.POST.get('total_copies', 0)
        copies_available = request.POST.get('copies_available', 0)

        # Convert copies to integers
        try:
            total_copies = int(total_copies)
            copies_available = int(copies_available)
        except ValueError:
            messages.error(request, "Total copies and copies available must be numbers.")
            context = {'book': book, 'page_title': page_title}
            return render(request, 'librarian_add_edit_book.html', context)

        if total_copies < copies_available:
            messages.error(request, "Copies available cannot exceed total copies.")
            context = {'book': book, 'page_title': page_title}
            return render(request, 'librarian_add_edit_book.html', context)

        if book_id: # Editing existing book
            # Check if google_books_id is unique if changed
            if google_books_id and google_books_id != book.google_books_id:
                if Book.objects.filter(google_books_id=google_books_id).exists():
                    messages.error(request, f"A book with Google Books ID '{google_books_id}' already exists.")
                    context = {'book': book, 'page_title': page_title}
                    return render(request, 'librarian_add_edit_book.html', context)
            
            book.google_books_id = google_books_id if google_books_id else book.google_books_id
            book.title = title
            book.author = author
            book.description = description
            book.image_url = image_url
            book.info_link = info_link
            book.total_copies = total_copies
            book.copies_available = copies_available
            try:
                book.save()
                messages.success(request, f"Book '{book.title}' updated successfully!")
                return redirect('librarian_book_management')
            except Exception as e:
                messages.error(request, f"Error updating book: {e}")
        else: # Adding new book
            # Check if google_books_id is unique
            if google_books_id and Book.objects.filter(google_books_id=google_books_id).exists():
                messages.error(request, f"A book with Google Books ID '{google_books_id}' already exists.")
                context = {'book': book, 'page_title': page_title}
                return render(request, 'librarian_add_edit_book.html', context)

            try:
                Book.objects.create(
                    google_books_id=google_books_id,
                    title=title,
                    author=author,
                    description=description,
                    image_url=image_url,
                    info_link=info_link,
                    total_copies=total_copies,
                    copies_available=copies_available
                )
                messages.success(request, f"New book '{title}' added successfully!")
                return redirect('librarian_book_management')
            except Exception as e:
                messages.error(request, f"Error adding book: {e}")
        
        context = {'book': book, 'page_title': page_title}
        return render(request, 'librarian_add_edit_book.html', context)

# NEW: View for Librarian Delete Book
@librarian_required
def librarian_delete_book(request, book_id):
    book = get_object_or_404(Book, id=book_id)
    if request.method == 'POST':
        try:
            book_title = book.title # Store title before deleting
            book.delete()
            messages.success(request, f"Book '{book_title}' deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting book: {e}")
        return redirect('librarian_book_management')
    
    # For GET request, confirm deletion
    context = {
        'book': book,
        'page_title': 'Confirm Delete Book',
    }
    return render(request, 'librarian_delete_book.html', context)



@librarian_required
def accept_buy_request(request, transaction_id):
    transaction_record = get_object_or_404(Borrowing, id=transaction_id, status='pending_purchase')

    if request.method == 'POST':
        book = transaction_record.book
        member = transaction_record.member # Get the member object
        
        if book.copies_available <= 0:
            messages.error(request, f"Cannot approve purchase: '{book.title}' is out of stock.")
            return redirect('librarian_dashboard')
        
        # Simulate a dynamic amount for the book (e.g., Rs. 500.00)
        # In a real app, this would come from a fixed price on the Book model
        purchase_amount_paise = 50000  # Amount in paise (e.g., 500.00 INR = 50000 paise)

        try:
            # Create a Razorpay order
            order_receipt = f"order_rcptid_{transaction_record.id}"
            razorpay_order = client.order.create({
                'amount': purchase_amount_paise, # Amount in paise
                'currency': 'INR',
                'receipt': order_receipt,
                'payment_capture': '1' # Auto capture payment
            })
            
            # Update transaction record with Razorpay order ID and amount, set status to payment_pending
            transaction_record.razorpay_order_id = razorpay_order['id']
            transaction_record.amount = purchase_amount_paise # Store in paise
            transaction_record.status = 'payment_pending'
            transaction_record.approval_date = timezone.now()

            librarian_id = request.session.get('user_id')
            if librarian_id:
                try:
                    librarian_approver = Librarian.objects.get(id=librarian_id)
                    transaction_record.approved_by = librarian_approver
                except Librarian.DoesNotExist:
                    messages.warning(request, "Librarian not found for approval record.")
            
            transaction_record.save()
            messages.success(request, f"Purchase request for '{transaction_record.book.title}' by {transaction_record.member.name} approved. Payment is now pending!")

            # NEW: Send email to member about approved request
            subject = f"Your BookHub Purchase Request for '{book.title}' Has Been Approved!"
            message = (
                f"Dear {member.name},\n\n"
                f"Your request to purchase '{book.title}' has been approved by our librarian.\n\n"
                f"Amount to pay: ₹{purchase_amount_paise / 100:.2f}\n"
                f"Please proceed to complete the payment through your dashboard or by clicking the link below:\n"
                f"{request.build_absolute_uri(redirect('initiate_payment_page', transaction_id=transaction_record.id).url)}\n\n"
                f"Thank you for using BookHub!\n"
                f"BookHub Team"
            )
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.email], fail_silently=False)
                logger.info(f"Email sent to {member.email} about approved request for {book.title}")
            except Exception as e:
                logger.error(f"Failed to send email to member about approved request: {e}")

            return redirect('librarian_dashboard')

        except Exception as e:
            logger.error(f"Error creating Razorpay order for transaction {transaction_id}: {e}")
            messages.error(request, f"Error approving purchase: Could not initiate payment. {e}")
            transaction_record.status = 'payment_failed' # Mark as failed if order creation fails
            transaction_record.save()
            
            # NEW: Send email to member about failed payment initiation (if applicable)
            subject = f"BookHub Purchase Request for '{book.title}' - Payment Initiation Failed"
            message = (
                f"Dear {member.name},\n\n"
                f"There was an issue initiating the payment for your purchase request of '{book.title}'.\n"
                f"Please try again later or contact support if the issue persists.\n\n"
                f"Error details: {e}\n\n"
                f"BookHub Team"
            )
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.email], fail_silently=False)
                logger.info(f"Email sent to {member.email} about failed payment initiation for {book.title}")
            except Exception as e:
                logger.error(f"Failed to send email to member about payment initiation failure: {e}")

            return redirect('librarian_dashboard')
    
    messages.error(request, "Invalid request for purchase acceptance.")
    return redirect('librarian_dashboard')

@librarian_required
def reject_buy_request(request, transaction_id):
    transaction_record = get_object_or_404(Borrowing, id=transaction_id, status='pending_purchase')

    if request.method == 'POST':
        member = transaction_record.member # Get the member object
        book = transaction_record.book # Get the book object

        transaction_record.status = 'rejected_purchase'
        transaction_record.approval_date = timezone.now()
        
        librarian_id = request.session.get('user_id')
        if librarian_id:
            try:
                librarian_approver = Librarian.objects.get(id=librarian_id)
                transaction_record.approved_by = librarian_approver
            except Librarian.DoesNotExist:
                messages.warning(request, "Librarian not found for rejection record.")
        
        transaction_record.save()
        messages.info(request, f"Purchase request for '{transaction_record.book.title}' by {transaction_record.member.name} rejected.")

        # NEW: Send email to member about rejected request
        subject = f"Your BookHub Purchase Request for '{book.title}' Has Been Rejected"
        message = (
            f"Dear {member.name},\n\n"
            f"Unfortunately, your request to purchase '{book.title}' has been rejected by our librarian.\n"
            f"This might be due to various reasons such as stock unavailability or other library policies.\n\n"
            f"Please contact the library if you have any questions.\n\n"
            f"BookHub Team"
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.email], fail_silently=False)
            logger.info(f"Email sent to {member.email} about rejected request for {book.title}")
        except Exception as e:
            logger.error(f"Failed to send email to member about rejected request: {e}")

        return redirect('librarian_dashboard')

    messages.error(request, "Invalid request for purchase rejection.")
    return redirect('librarian_dashboard')

@member_required
def payment_success(request, transaction_id):
    # This view will be called by Razorpay webhook or from client-side after payment success
    if request.method == 'POST':
        try:
            payment_id = request.POST.get('razorpay_payment_id')
            order_id = request.POST.get('razorpay_order_id')
            signature = request.POST.get('razorpay_signature')
            
            # Verify the payment signature to ensure authenticity
            params_dict = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            client.utility.verify_payment_signature(params_dict)

            transaction_record = get_object_or_404(Borrowing, id=transaction_id, razorpay_order_id=order_id, status='payment_pending')
            member = transaction_record.member # Get the member object
            book = transaction_record.book # Get the book object
            
            # Update transaction record for successful payment
            transaction_record.razorpay_payment_id = payment_id
            transaction_record.status = 'purchased'
            transaction_record.save()

            # Decrement book copies
            book.copies_available -= 1
            book.save()

            messages.success(request, f"Payment for '{book.title}' successful! Your purchase is complete.")
            
            # NEW: Send email to member about successful payment
            subject = f"Your BookHub Purchase for '{book.title}' is Complete!"
            message = (
                f"Dear {member.name},\n\n"
                f"Thank you for your purchase of '{book.title}'. Your payment was successful.\n"
                f"Amount Paid: ₹{transaction_record.amount / 100:.2f}\n"
                f"Razorpay Payment ID: {payment_id}\n\n"
                f"We hope you enjoy your new book!\n"
                f"BookHub Team"
            )
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.email], fail_silently=False)
                logger.info(f"Email sent to {member.email} about successful payment for {book.title}")
            except Exception as e:
                logger.error(f"Failed to send email to member about successful payment: {e}")

            # NEW: Send email to librarians about completed purchase
            librarians = Librarian.objects.all()
            if librarians.exists():
                subject_librarian = f"BookHub Purchase Completed: '{book.title}'"
                message_librarian = (
                    f"Dear Librarian,\n\n"
                    f"A purchase for '{book.title}' by {member.name} ({member.email}) has been successfully completed.\n"
                    f"Amount: ₹{transaction_record.amount / 100:.2f}\n"
                    f"Payment ID: {payment_id}\n"
                    f"Book stock for '{book.title}' has been updated.\n\n"
                    f"BookHub Team"
                )
                recipient_list_librarian = [lib.email for lib in librarians]
                try:
                    send_mail(subject_librarian, message_librarian, settings.DEFAULT_FROM_EMAIL, recipient_list_librarian, fail_silently=False)
                    logger.info(f"Email sent to librarians about completed purchase for {book.title}")
                except Exception as e:
                    logger.error(f"Failed to send email to librarians about completed purchase: {e}")

            return redirect('userpage')

        except Exception as e:
            logger.error(f"Razorpay payment verification failed for transaction {transaction_id}: {e}")
            transaction_record = get_object_or_404(Borrowing, id=transaction_id) # Fetch even if status is not payment_pending
            member = transaction_record.member # Get the member object
            book = transaction_record.book # Get the book object

            transaction_record.status = 'payment_failed'
            transaction_record.save()
            messages.error(request, f"Payment verification failed. Please try again or contact support. Error: {e}")
            
            # NEW: Send email to member about payment failure
            subject = f"BookHub Payment Failed for '{book.title}'"
            message = (
                f"Dear {member.name},\n\n"
                f"Your payment for '{book.title}' has failed.\n"
                f"Please check your payment details and try again. If the issue persists, contact support.\n\n"
                f"Error details: {e}\n\n"
                f"BookHub Team"
            )
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.email], fail_silently=False)
                logger.info(f"Email sent to {member.email} about payment failure for {book.title}")
            except Exception as e:
                logger.error(f"Failed to send email to member about payment failure: {e}")

            return redirect('userpage')
    
    messages.error(request, "Invalid request for payment success processing.")
    return redirect('userpage')


@librarian_required
def librarian_member_management(request):
    members = Member.objects.all().order_by('name')
    context = {
        'members': members,
        'page_title': 'Manage Members',
    }
    return render(request, 'librarian_member_management.html', context)

@librarian_required
@librarian_required
def librarian_view_member(request, member_id):
    member = get_object_or_404(Member, id=member_id)
    
    # Fetch all transactions (purchases) related to this member
    transactions_qs = Borrowing.objects.filter(member=member).select_related('book', 'approved_by').order_by('-request_date')

    # Process the queryset to create a list of dictionaries
    processed_transactions = []
    for transaction in transactions_qs:
        processed_transactions.append({
            'book': transaction.book,
            'status': transaction.status,
            'request_date': transaction.request_date,
            'approval_date': transaction.approval_date,
            'approved_by': transaction.approved_by,
            'amount': transaction.amount,
            'amount_display': transaction.amount / 100 if transaction.amount else 0, # <-- Perform calculation here
            'razorpay_order_id': transaction.razorpay_order_id,
            'razorpay_payment_id': transaction.razorpay_payment_id,
            'get_status_display': transaction.get_status_display() # Pass the display value
        })

    context = {
        'member': member,
        'member_transactions': processed_transactions, # Pass the processed list
        'page_title': f"Member Details: {member.name}",
    }
    return render(request, 'librarian_view_member.html', context)

@librarian_required
def librarian_toggle_member_status(request, member_id):
    member = get_object_or_404(Member, id=member_id)

    if request.method == 'POST':
        if hasattr(member, 'is_active'):
            member.is_active = not member.is_active
            member.save()
            status_message = "activated" if member.is_active else "deactivated"
            messages.success(request, f"Member '{member.name}' has been {status_message}.")
            
            # NEW: Send email notification to member about account status change
            subject = f"Your BookHub Account Status Has Changed"
            message = (
                f"Dear {member.name},\n\n"
                f"Your BookHub account has been {status_message} by a librarian.\n\n"
                f"If you have any questions, please contact the library.\n\n"
                f"BookHub Team"
            )
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [member.email], fail_silently=False)
                logger.info(f"Email sent to {member.email} about account status change.")
            except Exception as e:
                logger.error(f"Failed to send email to member about account status change: {e}")

        else:
            messages.error(request, "Member model does not have an 'is_active' field to toggle.")
        return redirect('librarian_member_management') # Redirect back to member list
    
    messages.error(request, "Invalid request for toggling member status.")
    return redirect('librarian_member_management')

# NEW: View for Librarian Reports/Analytics
@librarian_required
def librarian_reports(request):
    # 1. Transaction Status Distribution
    # Group by status and count transactions
    transaction_status_data = Borrowing.objects.values('status').annotate(count=Count('id'))
    
    # Prepare data for Chart.js Pie Chart
    status_labels = []
    status_counts = []
    status_colors = []
    
    # Define colors for each status for consistency
    status_color_map = {
        'pending_purchase': '#ffc107', # Warning - Yellow
        'payment_pending': '#0dcaf0',  # Info - Cyan
        'purchased': '#28a745',       # Success - Green
        'rejected_purchase': '#dc3545', # Danger - Red
        'payment_failed': '#6c757d',    # Secondary - Grey
    }

    for item in transaction_status_data:
        # Use get_status_display to get human-readable status
        display_name = next((choice[1] for choice in Borrowing.STATUS_CHOICES if choice[0] == item['status']), item['status'].replace('_', ' ').title())
        status_labels.append(display_name)
        status_counts.append(item['count'])
        status_colors.append(status_color_map.get(item['status'], '#6c757d')) # Default to grey if status not mapped

    # 2. Most Purchased Books (Top 5)
    # Filter for 'purchased' status, group by book, and count purchases
    top_books_data = Borrowing.objects.filter(status='purchased') \
                                    .values('book__title', 'book__author') \
                                    .annotate(purchase_count=Count('book__id')) \
                                    .order_by('-purchase_count')[:5] # Limit to top 5

    # Prepare data for Chart.js Bar Chart or simple list
    top_book_titles = []
    top_book_counts = []
    for item in top_books_data:
        title = item['book__title']
        author = item['book__author'] if item['book__author'] else "Unknown"
        top_book_titles.append(f"{title} ({author})")
        top_book_counts.append(item['purchase_count'])

    # 3. Total Revenue from Purchases
    total_revenue_paise = Borrowing.objects.filter(status='purchased').aggregate(total_amount=Sum('amount'))['total_amount'] or 0
    total_revenue_inr = total_revenue_paise / 100.0

    # 4. Active vs. Inactive Members
    member_status_data = Member.objects.values('is_active').annotate(count=Count('id'))
    active_members_count = 0
    inactive_members_count = 0
    for item in member_status_data:
        if item['is_active']:
            active_members_count = item['count']
        else:
            inactive_members_count = item['count']
    total_members_count = active_members_count + inactive_members_count


    context = {
        'page_title': 'Library Reports & Analytics',
        'transaction_status_labels': json.dumps(status_labels),
        'transaction_status_counts': json.dumps(status_counts),
        'transaction_status_colors': json.dumps(status_colors),
        'top_book_titles': json.dumps(top_book_titles),
        'top_book_counts': json.dumps(top_book_counts),
        'total_revenue_inr': total_revenue_inr,
        'active_members_count': active_members_count,
        'inactive_members_count': inactive_members_count,
        'total_members_count': total_members_count,
    }
    return render(request, 'librarian_reports.html', context)

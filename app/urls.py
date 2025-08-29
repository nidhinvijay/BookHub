# core/urls.py
from django.contrib import admin
from django.urls import path,include
from . import views

urlpatterns = [
    path('',views.home, name='home'),
    path('browse-books/', views.browse_books, name='browse_books'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_member, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('userpage/' ,views.userpage, name='userpage'),

    # Path for buying request - This now redirects to the book detail page
    path('buy-request/<str:google_books_id>/', views.buy_request_view, name='buy_request'),

    # Paths for librarian actions related to purchases
    path('librarian-dashboard/', views.librarian_dashboard, name='librarian_dashboard'),
    path('librarian/accept/<int:transaction_id>/', views.accept_buy_request, name='accept_buy_request'),
    path('librarian/reject/<int:transaction_id>/', views.reject_buy_request, name='reject_buy_request'),
    
    # New path for Razorpay payment success callback
    path('payment-success/<int:transaction_id>/', views.payment_success, name='payment_success'),

    # New path for the dedicated payment initiation page
    path('payment/<int:transaction_id>/', views.initiate_payment_page, name='initiate_payment_page'),

    # Path for individual book details page
    path('book/<str:google_books_id>/', views.book_detail, name='book_detail'),

    # Path for member profile editing
    path('profile/edit/', views.member_profile_edit, name='member_profile_edit'),

    # Paths for Librarian Book Management
    path('librarian/books/', views.librarian_book_management, name='librarian_book_management'),
    path('librarian/books/add/', views.librarian_add_book, name='librarian_add_book'), # <-- Points to new view
    path('librarian/books/edit/<int:book_id>/', views.librarian_edit_book, name='librarian_edit_book'), # <-- Points to new view
    path('librarian/books/delete/<int:book_id>/', views.librarian_delete_book, name='librarian_delete_book'),

    # Paths for Librarian User Management
    path('librarian/members/', views.librarian_member_management, name='librarian_member_management'),
    path('librarian/members/view/<int:member_id>/', views.librarian_view_member, name='librarian_view_member'),
    path('librarian/members/toggle-status/<int:member_id>/', views.librarian_toggle_member_status, name='librarian_toggle_member_status'),

    # NEW: Path for Librarian Reports/Analytics
    path('librarian/reports/', views.librarian_reports, name='librarian_reports'),
]

# core/models.py
from django.db import models
from django.utils import timezone

class Member(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    joined_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True) # NEW FIELD: For toggling member status

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Patron" # Custom singular name for admin
        verbose_name_plural = "Patrons" # Custom plural name for admin

class Librarian(models.Model):
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    name = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name or self.email

    class Meta:
        verbose_name = "Library Staff Member" # Custom singular name for admin
        verbose_name_plural = "Library Staff" # Custom plural name for admin

class Book(models.Model):
    google_books_id = models.CharField(max_length=255, unique=True, db_index=True)    
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=500, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    image_url = models.URLField(max_length=1000, blank=True, null=True) # URL for the book cover
    info_link = models.URLField(max_length=1000, blank=True, null=True) # Link to Google Books page
    total_copies = models.IntegerField(default=1) # Total copies this library owns (now represents total stock)
    copies_available = models.IntegerField(default=1) # Copies currently available for purchase

    def __str__(self):
        return f"{self.title} by {self.author or 'Unknown'}"

    class Meta:
        verbose_name = "Book Item" # Custom singular name for admin
        verbose_name_plural = "Book Stock" # Custom plural name for admin

class Borrowing(models.Model): # Now represents a purchase transaction
    # Defines the possible states of a purchase request/record
    STATUS_CHOICES = [
        ('pending_purchase', 'Pending Purchase Approval'), # Member requested to buy
        ('payment_pending', 'Payment Pending'),            # Librarian approved, awaiting member payment
        ('purchased', 'Purchased'),                        # Member completed payment
        ('rejected_purchase', 'Rejected Purchase'),        # Librarian rejected the request
        ('payment_failed', 'Payment Failed'),              # Payment attempted but failed
    ]
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='transactions')
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='transactions')
    
    request_date = models.DateTimeField(auto_now_add=True)
    approval_date = models.DateTimeField(blank=True, null=True) # When librarian approves/rejects
    due_date = models.DateTimeField(blank=True, null=True) # Can be repurposed for delivery date if needed, or removed
    return_date = models.DateTimeField(blank=True, null=True) # Not relevant for purchase, can be removed

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_purchase')
    
    approved_by = models.ForeignKey(Librarian, on_delete=models.SET_NULL, blank=True, null=True, related_name='approved_transactions')

    # New field for Razorpay Order ID
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True) # Removed unique=True as it might not be unique across all transactions if an order fails and is retried
    # New field for Razorpay Payment ID (after successful payment)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True) # Removed unique=True as it might not be unique across all transactions if a payment fails and is retried
    # New field for payment amount (in smallest unit, e.g., paise for INR)
    amount = models.IntegerField(default=0) # Store amount in integer (e.g., paise for INR)

    def __str__(self):
        return f"{self.member.name} requested to buy {self.book.title} (Status: {self.status})"

    class Meta:
        # Ensures a member can only have one active (pending or payment pending) request for the same book
        unique_together = [
            ('member', 'book', 'status'), # This needs adjustment, as status will change
        ]
        # Better: Ensure unique on (member, book) where status is not 'rejected_purchase' or 'payment_failed'
        # For simplicity in this example, we'll rely on view logic to prevent duplicates for 'pending_purchase'
        # and 'payment_pending' states.
        verbose_name = "Purchase Transaction" # Custom singular name for admin
        verbose_name_plural = "Purchase Transactions" # Custom plural name for admin

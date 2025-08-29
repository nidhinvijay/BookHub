# core/admin.py
from django.contrib import admin
from .models import Member, Librarian, Book, Borrowing

# Admin configuration for Member model
@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'joined_date')
    search_fields = ('name', 'email', 'phone_number')
    list_filter = ('joined_date',)

# Admin configuration for Librarian model
@admin.register(Librarian)
class LibrarianAdmin(admin.ModelAdmin):
    list_display = ('name', 'email')
    search_fields = ('name', 'email')

# Admin configuration for Book model
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'copies_available', 'total_copies', 'google_books_id')
    search_fields = ('title', 'author', 'google_books_id')
    list_filter = ('copies_available',)
    list_editable = ('copies_available', 'total_copies') # Allow direct editing of stock


# Admin configuration for Borrowing (now Purchase Transaction) model
@admin.register(Borrowing)
class PurchaseTransactionAdmin(admin.ModelAdmin): # Renamed class for clarity in admin.py
    list_display = (
        'member',
        'book',
        'transaction_status',  # Custom method for "Purchase Status"
        'amount_display',      # Custom method for "Amount Paid"
        'requested_on',        # Custom method for "Requested Date"
        'approved_on',         # Custom method for "Approval Date"
        'razorpay_order_id',
        'razorpay_payment_id',
        'approved_by_librarian' # Custom method for "Approved By"
    )
    list_filter = ('status', 'request_date', 'approval_date', 'approved_by')
    search_fields = (
        'member__name',
        'member__email',
        'book__title',
        'book__author',
        'razorpay_order_id',
        'razorpay_payment_id'
    )
    readonly_fields = (
        'request_date',
        'approval_date',
        'razorpay_order_id',
        'razorpay_payment_id',
        'amount',
    )
    fieldsets = (
        (None, {
            'fields': ('member', 'book', 'status', 'amount')
        }),
        ('Transaction Dates & Approver', { # More descriptive fieldset title
            'fields': ('request_date', 'approval_date', 'approved_by'),
            'classes': ('collapse',)
        }),
        ('Payment Gateway Details', { # More descriptive fieldset title
            'fields': ('razorpay_order_id', 'razorpay_payment_id'),
            'classes': ('collapse',)
        }),
    )

    # Custom method to display amount in rupees (since it's stored in paise)
    def amount_display(self, obj):
        return f"₹{obj.amount / 100:.2f}" if obj.amount else "₹0.00"
    amount_display.short_description = 'Amount Paid' # Custom column header

    # Custom method to display transaction status with a more descriptive header
    def transaction_status(self, obj):
        return obj.get_status_display()
    transaction_status.short_description = 'Purchase Status' # Custom column header
    transaction_status.admin_order_field = 'status' # Allows sorting by the actual status field

    # Custom method for the request date column header
    def requested_on(self, obj):
        return obj.request_date.strftime('%Y-%m-%d %H:%M') if obj.request_date else 'N/A'
    requested_on.short_description = 'Requested Date' # Custom column header
    requested_on.admin_order_field = 'request_date'

    # Custom method for the approval date column header
    def approved_on(self, obj):
        return obj.approval_date.strftime('%Y-%m-%d %H:%M') if obj.approval_date else 'N/A'
    approved_on.short_description = 'Approval Date' # Custom column header
    approved_on.admin_order_field = 'approval_date'

    # Custom method for the approved_by column header
    def approved_by_librarian(self, obj):
        return obj.approved_by.name if obj.approved_by else 'N/A'
    approved_by_librarian.short_description = 'Approved By' # Custom column header
    approved_by_librarian.admin_order_field = 'approved_by'


    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Prefetch related objects to reduce database queries for list_display fields
        return qs.select_related('member', 'book', 'approved_by')

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.razorpay_order_id = None
            obj.razorpay_payment_id = None
        super().save_model(request, obj, form, change)


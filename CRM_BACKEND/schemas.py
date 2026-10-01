from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal

class SignupRequest(BaseModel):
    name: str
    email: str
    role: str
    phone: str
    password: str
    employee_id: Optional[str] = None

class LoginRequest(BaseModel):
    employee_id: str
    password: str

class LocationUpdate(BaseModel):
    lat: float
    lon: float
    checkout_note: Optional[str] = None

class PinLocationRequest(BaseModel):
    lat: float
    lon: float
    note: str

class ActivityLogCreate(BaseModel):
    action: str
    details: str


class LeadCreate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    status: Optional[str] = "pending"
    note: Optional[str] = None
    source: Optional[str] = "Manual"
    location: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = "Medium"
    product_type: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gsm: Optional[str] = None
    quantity: Optional[int] = None
    handles: Optional[str] = None
    print_color: Optional[str] = None
    bag_type: Optional[str] = None
    print_side: Optional[str] = None
    followup_date: Optional[date] = None
    lead_value: Optional[Decimal] = None
    expected_delivery_date: Optional[date] = None
    unit_price: Optional[Decimal] = None
    stereo_charge: Optional[Decimal] = None
    stereo_count: Optional[int] = None
    color_addon: Optional[Decimal] = None
    gst_rate: Optional[Decimal] = None
    gst_amount: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    status: str
    note: Optional[str] = None
    source: Optional[str] = "Manual"
    location: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[str] = "Medium"
    product_type: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gsm: Optional[str] = None
    quantity: Optional[int] = None
    handles: Optional[str] = None
    print_color: Optional[str] = None
    bag_type: Optional[str] = None
    print_side: Optional[str] = None
    followup_date: Optional[date] = None
    lead_value: Optional[Decimal] = None
    expected_delivery_date: Optional[date] = None
    unit_price: Optional[Decimal] = None
    stereo_charge: Optional[Decimal] = None
    stereo_count: Optional[int] = None
    color_addon: Optional[Decimal] = None
    gst_rate: Optional[Decimal] = None
    gst_amount: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None

class DealCreate(BaseModel):
    deal_name: str
    company_name: str
    contact_name: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    deal_value: Decimal = 0
    source: Optional[str] = ""
    note: Optional[str] = ""
    assigned_to: Optional[str] = None
    product_type: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gsm: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    advance_received: Optional[Decimal] = None
    balance_amount: Optional[Decimal] = None
    expected_delivery_date: Optional[date] = None
    handles: Optional[str] = None
    print_color: Optional[str] = None
    bag_type: Optional[str] = None
    print_side: Optional[str] = None
    location: Optional[str] = None
    priority: Optional[str] = None
    followup_date: Optional[date] = None

class DealUpdate(BaseModel):
    deal_name: Optional[str] = None
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = ""
    email: Optional[str] = ""
    deal_value: Decimal = 0
    source: Optional[str] = ""
    note: Optional[str] = None
    assigned_to: Optional[str] = None
    product_type: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gsm: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    advance_received: Optional[Decimal] = None
    balance_amount: Optional[Decimal] = None
    expected_delivery_date: Optional[date] = None
    handles: Optional[str] = None
    print_color: Optional[str] = None
    bag_type: Optional[str] = None
    print_side: Optional[str] = None
    location: Optional[str] = None
    priority: Optional[str] = None
    followup_date: Optional[date] = None

class LeadConvertRequest(BaseModel):
    product_type: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    gsm: Optional[str] = None
    quantity: int
    unit_price: Decimal
    lead_value: Optional[Decimal] = None
    order_value: Optional[Decimal] = None
    handles: Optional[str] = None
    print_color: Optional[str] = None
    bag_type: Optional[str] = None
    print_side: Optional[str] = None
    expected_delivery_date: Optional[date] = None
    customer_id: Optional[int] = None
    stereo_charge: Optional[Decimal] = None
    stereo_count: Optional[int] = None
    color_addon: Optional[Decimal] = None
    gst_rate: Optional[Decimal] = None
    gst_amount: Optional[Decimal] = None
    grand_total: Optional[Decimal] = None
    advance_received: Optional[Decimal] = None
    balance_amount: Optional[Decimal] = None

class InventoryItemCreate(BaseModel):
    item_name: str
    category: str
    unit: Optional[str] = None
    current_stock: Decimal = 0
    minimum_stock: Decimal = 0
    unit_price: Optional[Decimal] = 0

class InventoryItemUpdate(BaseModel):
    item_name: str
    category: str
    unit: Optional[str] = None
    current_stock: Decimal
    minimum_stock: Decimal
    unit_price: Optional[Decimal] = 0

class PurchaseRequestCreate(BaseModel):
    item_name: str
    quantity: Decimal
    vendor_name: Optional[str] = None

class ProductionUpdate(BaseModel):
    status: str
    expected_completion_date: Optional[date] = None
    remarks: Optional[str] = None

class InvoiceCreate(BaseModel):
    order_id: int
    invoice_number: str
    subtotal: Decimal
    gst: Optional[Decimal] = 0
    transport_charge: Optional[Decimal] = 0
    stereo_charge: Optional[Decimal] = 0
    total_amount: Decimal
    payment_status: Optional[str] = "PENDING"

from typing import Optional, List, Union

class InvoicePaymentUpdate(BaseModel):
    payment_status: Optional[str] = None
    amount_received: Optional[Union[float, Decimal, str]] = None

class CustomerCreate(BaseModel):
    company_name: Optional[str] = None
    contact_person: str
    phone: str
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    notes: Optional[str] = None

class IndentCreate(BaseModel):
    item_name: str
    size: str
    quantity: Decimal

class ReminderCreate(BaseModel):
    title: str
    description: Optional[str] = None
    remind_at: datetime
    category: Optional[str] = "Other"

class UserUpdate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    salary: Optional[float] = None
    department: Optional[str] = None
    designation: Optional[str] = None
    joining_date: Optional[str] = None
    is_active: Optional[bool] = None
    biometric_id: Optional[str] = None

class EmployeeConvertRequest(BaseModel):
    password: str
    salary: Optional[float] = 0.0
    department: Optional[str] = ""
    designation: Optional[str] = ""
    biometric_id: Optional[str] = ""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    employee_id: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    employee_id: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ApprovePasswordChangeRequest(BaseModel):
    new_password: str

class SendQuoteRequest(BaseModel):
    quoted_price: float
    unit_price: Optional[float] = None
    custom_note: Optional[str] = None
    recipient_email: Optional[str] = None
    stereo_charge: Optional[float] = 0.0
    stereo_count: Optional[int] = 0
    color_addon: Optional[float] = 0.0
    gst_rate: Optional[float] = 5.0
    gst_amount: Optional[float] = 0.0
    grand_total: Optional[float] = None

class RemindClientRequest(BaseModel):
    custom_note: Optional[str] = None
    recipient_email: Optional[str] = None

class SendInvoiceRequest(BaseModel):
    custom_note: Optional[str] = None
    recipient_email: Optional[str] = None

class ProductRateCardCreate(BaseModel):
    category: str
    size: str
    size_normalized: Optional[str] = None
    gsm_rates: Optional[dict] = None
    base_weight_kg: Optional[float] = None
    pieces_per_kg: Optional[float] = None
    rate_per_kg_high: Optional[float] = None
    rate_per_kg_low: Optional[float] = None
    default_handles: Optional[str] = None
    default_bag_type: Optional[str] = None
    min_order_qty: Optional[int] = 500
    stereo_default_price: Optional[float] = 1770.0
    color_addon_rules: Optional[dict] = None
    gst_rate: Optional[float] = 5.0
    tissue_type: Optional[str] = None
    high_rate: Optional[float] = None
    low_rate: Optional[float] = None
    is_active: Optional[bool] = True

class ProductRateCardUpdate(BaseModel):
    category: Optional[str] = None
    size: Optional[str] = None
    size_normalized: Optional[str] = None
    gsm_rates: Optional[dict] = None
    base_weight_kg: Optional[float] = None
    pieces_per_kg: Optional[float] = None
    rate_per_kg_high: Optional[float] = None
    rate_per_kg_low: Optional[float] = None
    default_handles: Optional[str] = None
    default_bag_type: Optional[str] = None
    min_order_qty: Optional[int] = None
    stereo_default_price: Optional[float] = None
    color_addon_rules: Optional[dict] = None
    gst_rate: Optional[float] = None
    tissue_type: Optional[str] = None
    high_rate: Optional[float] = None
    low_rate: Optional[float] = None
    is_active: Optional[bool] = None





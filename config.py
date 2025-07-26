# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Configuration ---
API_BASE_URL = os.getenv("API_BASE_URL", "https://10.216.70.62/DEV/litellm")
API_KEY = os.getenv("API_KEY", "sk-gWXqVa4oxbt-9HnWHHBdsg")
API_MODEL = os.getenv("API_MODEL", "gemini-2.5-flash")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", 600)) # Increased timeout
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", 50))
API_CONCURRENCY_LIMIT = int(os.getenv("API_CONCURRENCY_LIMIT", 1))
EXPONENTIAL_BACKOFF_FACTOR = float(os.getenv("EXPONENTIAL_BACKOFF_FACTOR", 1.5))

SUPPORTED_MIME_TYPES = {
    "application/pdf": "PDF",
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
}

SUPPORTED_FILE_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"]

TEMP_DIR = "temp_processing"
OUTPUT_FILENAME = "extracted_data.csv"
JSON_CORRECTION_ATTEMPTS = 3 # Correction attempts per group

LOG_FILE = "app_log.log"
LOG_LEVEL = "INFO"

# --- Column Order Configuration ---
EXCEL_COLUMN_ORDER = [
    # === Core fields ===
    "CASE_ID",
    "GROUP_Basename",
    "CLASSIFIED_Type",

    # === Fields for CRL ===
    "CRL_DATE & TIME OF RECEIPT OF DOCUMENT_Value",
    "CRL_TRANSACTION Product Code Selection_Value",
    "CRL_CUSTOMER REQUEST LETTER DATE_Value",
    "CRL_DESCRIPTION OF GOODS_Value",
    "CRL_TYPE OF GOODS_Value",
    "CRL_MODE OF REMITTANCE_Value",
    "CRL_APPLICANT NAME_Value",
    "CRL_APPLICANT ADDRESS_Value",
    "CRL_APPLICANT COUNTRY_Value",
    "CRL_DEBIT ACCOUNT NO_Value",
    "CRL_FEE ACCOUNT NO_Value",
    "CRL_REMITTANCE AMOUNT_Value",
    "CRL_REMITTANCE CURRENCY_Value",
    "CRL_CURRENCY AND AMOUNT OF REMITTANCE IN WORDS_Value",
    "CRL_BENEFICIARY NAME_Value",
    "CRL_BENEFICIARY ADDRESS_Value",
    "CRL_BENEFICIARY COUNTRY_Value",
    "CRL_BENEFICIARY ACCOUNT NO / IBAN_Value",
    "CRL_BENEFICIARY BANK_Value",
    "CRL_BENEFICIARY BANK ADDRESS_Value",
    "CRL_BENEFICIARY BANK SWIFT CODE / SORT CODE/ BSB / IFS CODE_Value",
    "CRL_FB CHARGES_Value",
    "CRL_INTERMEDIARY BANK NAME_Value",
    "CRL_INTERMEDIARY BANK ADDRESS_Value",
    "CRL_INTERMEDIARY BANK COUNTRY_Value",
    "CRL_INTERMEDIARY BANK SWIFT_Value",
    "CRL_LATEST SHIPMENT DATE_Value",
    "CRL_DISPATCH PORT_Value",
    "CRL_DELIVERY PORT_Value",
    "CRL_HS CODE_Value",
    "CRL_IMPORT LICENSE DETAILS_Value",
    "CRL_COUNTRY OF ORIGIN_Value",
    "CRL_INVOICE NO_Value",
    "CRL_INVOICE DATE_Value",
    "CRL_INVOICE VALUE_Value",
    "CRL_SPECIFIC REFERENCE FOR SWIFT FIELD 70/72_Value",
    "CRL_TREASURY REFERENCE NO_Value",
    "CRL_STANDARD DECLARATIONS AS PER PRODUCTS_Value",
    "CRL_TRANSACTION EVENT_Value",
    "CRL_CRL DATE_Value",
    "CRL_INCO TERM_Value",
    "CRL_THIRD PARTY EXPORTER NAME_Value",
    "CRL_THIRD PARTY EXPORTER COUNTRY_Value",
    "CRL_EXCHANGE RATE_Value",
    "CRL_APPLICANT SIGNATURE_Value",
    "CRL_CUSTOMER SIGNATURE_Value",

    # === Fields for Invoice ===
    "INVOICE_TYPE OF INVOICE - COMMERCIAL/PROFORMA/CUSTOMS_Value",
    "INVOICE_INVOICE DATE_Value",
    "INVOICE_INVOICE NO_Value",
    "INVOICE_BUYER NAME_Value",
    "INVOICE_BUYER ADDRESS_Value",
    "INVOICE_BUYER COUNTRY_Value",
    "INVOICE_SELLER NAME_Value",
    "INVOICE_SELLER ADDRESS_Value",
    "INVOICE_SELLER COUNTRY_Value",
    "INVOICE_INVOICE CURRENCY_Value",
    "INVOICE_INVOICE AMOUNT/VALUE_Value",
    "INVOICE_INVOICE AMOUNT/VALUE IN WORDS_Value",
    "INVOICE_BENEFICIARY ACCOUNT NO / IBAN_Value",
    "INVOICE_BENEFICIARY BANK_Value",
    "INVOICE_BENEFICIARY BANK ADDRESS_Value",
    "INVOICE_BENEFICIARY BANK SWIFT CODE / SORT CODE/ BSB / IFS CODE / ROUTING NO_Value",
    "INVOICE_Total Invoice Amount_Value",
    "INVOICE_Invoice Amount_Value",
    "INVOICE_Beneficiary Name_Value",
    "INVOICE_Beneficiary Address_Value",
    "INVOICE_DESCRIPTION OF GOODS_Value",
    "INVOICE_QUANTITY OF GOODS_Value",
    "INVOICE_PAYMENT TERMS_Value",
    "INVOICE_BENEFICIARY/SELLER'S SIGNATURE_Value",
    "INVOICE_APPLICANT/BUYER'S SIGNATURE_Value",
    "INVOICE_MODE OF REMITTANCE_Value",
    "INVOICE_MODE OF TRANSIT_Value",
    "INVOICE_INCO TERM_Value",
    "INVOICE_HS CODE_Value",
    "INVOICE_Intermediary Bank (Field 56)_Value",
    "INVOICE_INTERMEDIARY BANK NAME_Value",
    "INVOICE_INTERMEDIARY BANK ADDRESS_Value",
    "INVOICE_INTERMEDIARY BANK COUNTRY_Value",
    "INVOICE_Party Name ( Applicant )_Value",
    "INVOICE_Party Name ( Beneficiary )_Value",
    "INVOICE_Party Country ( Beneficiary )_Value",
    "INVOICE_Party Type ( Beneficiary Bank )_Value",
    "INVOICE_Party Name ( Beneficiary Bank )_Value",
    "INVOICE_Party Country ( Beneficiary Bank )_Value",
    "INVOICE_Drawee Address_Value",
    "INVOICE_PORT OF LOADING_Value",
    "INVOICE_PORT OF DISCHARGE_Value",
    "INVOICE_VESSEL TYPE_Value",
    "INVOICE_VESSEL NAME_Value",
    "INVOICE_THIRD PARTY EXPORTER NAME_Value",
    "INVOICE_THIRD PARTY EXPORTER COUNTRY_Value",

    # === Fields for Other Requirements ===
    "Processing_Status",
    "CLASSIFICATION_Confidence",
    "CLASSIFICATION_Reasoning",
]

# --- RESTRUCTURED DOCUMENT FIELD DEFINITIONS ---
DOCUMENT_FIELDS = {
    "CRL": {
        "ApplicantInfo": [
            {"name": "APPLICANT NAME", "description": "Objective: Extract the applicant's full name.\n- Labels: ['Applicant:', 'From:', 'Customer Name:', 'Remitter:']\n- Location: Usually in the header or a dedicated 'Applicant Details' section of the letter.\n- Note: Extract the full legal name, including suffixes."},
            {"name": "APPLICANT ADDRESS", "description": "Objective: Extract the applicant's complete mailing address.\n- Location: Usually follows the Applicant Name. Do not include the applicant's name in the address string."},
            {"name": "APPLICANT COUNTRY", "description": "Objective: Extract the applicant's country as a 2-letter ISO code.\n- Location: Usually the last part of the applicant's address.\n- Action: Identify the full country name, then convert to its ISO 3166-1 alpha-2 code (e.g., 'India' -> 'IN', 'United States' -> 'US')."},
            {"name": "DEBIT ACCOUNT NO", "description": "Objective: Extract the primary applicant account number for the main debit.\n- Labels: ['Debit Account No.:', 'Account to be Debited:', 'INR A/C No:']\n- Note: This is the source account for the remittance amount, not bank charges. Capture all digits exactly. Validate it looks like a real account number (e.g. 9-18 digits for India)."},
            {"name": "FEE ACCOUNT NO", "description": "Objective: Extract the account number for bank charges.\n- Location: Find row 'Account to be debited for charges'.\n- Logic: If 'on us' is selected and an account number is given, extract it. If 'on beneficiary' is selected, return null. If 'on us' is selected but no number is given, use the main DEBIT ACCOUNT NO."},
            {"name": "APPLICANT SIGNATURE", "description": "Objective: Find evidence of applicant's signature/authorization.\n- Location: Typically in a signature block at the end of the document.\n- Keywords: ['Authorized Signatory', 'For [Company Name]', 'Signature', 'Signed by:']\n- What to Extract: The typed name and title of the signatory if present. If only a handwritten signature is visible, return 'Signature Present'."},
            {"name": "CUSTOMER SIGNATURE", "description": "Objective: Find evidence of customer's signature. Synonymous with 'APPLICANT SIGNATURE'.\n- Location: Signature block at the end.\n- Keywords: ['Customer Signature', 'Authorized Signatory', 'For [Company Name]']\n- What to Extract: Typed name and title, or 'Signature Present' if handwritten."},
        ],
        "BeneficiaryInfo": [
            {"name": "BENEFICIARY NAME", "description": "Objective: Extract the full legal name of the beneficiary (payee/seller).\n- Labels: ['Beneficiary:', 'Payee:', 'Pay to:', 'To (Beneficiary):', 'Supplier Name:', 'Seller Name:']\n- Content: A company or individual's full name, including legal suffixes (e.g., Ltd., Inc., GmbH).\n- Note: Distinguish from Applicant, Bank, or intermediary names."},
            {"name": "BENEFICIARY ADDRESS", "description": "Objective: Extract the beneficiary's complete mailing address.\n- Location: Usually follows the Beneficiary Name.\n- Content: Should include street, city, state, postal code. Do not include the beneficiary's name in the address string."},
            {"name": "BENEFICIARY COUNTRY", "description": "Objective: Extract the beneficiary's country.\n- Labels: ['Country:', 'Beneficiary Country:']\n- Location: Usually the last part of the beneficiary's address or in a dedicated field."},
            {"name": "BENEFICIARY ACCOUNT NO / IBAN", "description": "Objective: Extract the beneficiary's bank account number or IBAN.\n- Labels: ['Account No.:', 'A/C No.:', 'IBAN:', 'Acc No:']\n- Location: Within beneficiary or bank details section.\n- Content: Can be a variable length account number or a structured IBAN (starts with 2-letter country code).\n- Note: Crucially, capture all digits accurately, especially repeated ones (e.g., '00', '111'). Prioritize IBAN if both are present."},
        ],
        "BankInfo": [
            {"name": "BENEFICIARY BANK", "description": "Objective: Extract the beneficiary's bank name.\n- Labels: ['Beneficiary Bank:', 'Bank Name:', 'Receiving Bank:']\n- Location: Near the beneficiary account number and SWIFT code. Often found in a structured table or field for bank details.\n- Note: Extract the full official name, including suffixes like 'PLC', 'N.A.', 'AG'."},
            {"name": "BENEFICIARY BANK ADDRESS", "description": "Objective: Extract the beneficiary bank's full mailing address.\n- Location: Usually follows the Beneficiary Bank Name. Do not include the bank's name in the address string."},
            {"name": "BENEFICIARY BANK SWIFT CODE / SORT CODE/ BSB / IFS CODE", "description": "Objective: Extract the bank's 11-char SWIFT/BIC. If not found, get other codes.\n- Primary Target (SWIFT): Look for 'SWIFT Code:', 'BIC Code:'. Must be 8 or 11 alphanumeric chars.\n- Normalization: Convert diacritics (é->e). - Fallback Targets: If no SWIFT, find 'IFSC', 'Sort Code', 'BSB', or 'ABA' number.\n- Output: Return the normalized 11-char SWIFT code, or the first valid fallback identifier found (e.g., 'IFSC: HDFC0000123')."},
            {"name": "INTERMEDIARY BANK NAME", "description": "Objective: Extract the Intermediary or Correspondent bank's name, if present.\n- Labels: ['Intermediary Bank:', 'Correspondent Bank:']\n- Location: In a dedicated section for payment routing, separate from the beneficiary bank."},
            {"name": "INTERMEDIARY BANK ADDRESS", "description": "Objective: Extract the Intermediary bank's full mailing address, if present.\n- Location: Follows the Intermediary Bank Name. Do not include the bank's name in the address string."},
            {"name": "INTERMEDIARY BANK COUNTRY", "description": "Objective: Extract the Intermediary bank's country, if present.\n- Location: Last part of the Intermediary bank's address."},
            {"name": "INTERMEDIARY BANK SWIFT", "description": "Objective: Extract the Intermediary bank's 11-char SWIFT/BIC, if present.\n- Target: Look for 'SWIFT Code:' within the Intermediary Bank details.\n- Normalization: If 8 chars, append 'XXX'. Convert diacritics (é->e).\n- Output: Return the normalized 11-char SWIFT code. Return null if not found."},
        ],
        "TransactionInfo": [
            {"name": "DATE & TIME OF RECEIPT OF DOCUMENT", "description": "Objective: Extract date and time from a circular seal stamp.\n- Structure: Look for a circular stamp with an inner circle for the date and an outer 24-hour time ring.\n- Date: Extract the date from the inner circle.\n- Time Logic: Time is based on the **leading edge** of a triangular arrow pointing to the outer ring.\n- Rule A (On the Line): If the leading edge is *exactly* on a major hour line 'H', time is (H-1):00. (e.g., on '12' is 11:00, on '00' is 23:00).\n- Rule B (In the Slot): If the leading edge is *past* major hour line 'H', the hour is 'H'. Minutes are determined by which 15-minute quadrant of the slot it occupies (:00, :15, :30, :45).\n- Format: Combine into 'DD-MM-YYYY HH:MM'. Return null if not found."},
            {"name": "CUSTOMER REQUEST LETTER DATE", "description": "Objective: Extract the date the customer/applicant wrote the letter.\n- Labels: ['Date:', 'Dated:', 'Letter Date:']\n- Location: Typically in the header near applicant details or near the signature.\n- Note: This is the authorship date of the letter, not other dates like invoice or receipt dates.\n- Format: 'DD-MM-YYYY'."},
            {"name": "REMITTANCE CURRENCY", "description": "Objective: Extract the three-letter ISO 4217 currency code for the transaction.\n- Labels: ['Currency:', 'CCY:', 'Transaction Currency:']\n- Location: Next to or preceding the remittance amount.\n- Format: A 3-letter uppercase code (e.g., USD, EUR, INR)."},
            {"name": "REMITTANCE AMOUNT", "description": "Objective: Extract the principal numerical amount to be remitted.\n- Labels: ['Amount:', 'Transaction Amount:', 'Remittance Amount:', 'Value:']\n- Location: Near the remittance currency.\n- Note: Extract figures, not words. Exclude currency symbols and thousands separators, but keep the decimal separator."},
            {"name": "CURRENCY AND AMOUNT OF REMITTANCE IN WORDS", "description": "Objective: Extract the remittance amount written in words.\n- Labels: ['Amount in Words:', 'Sum of ... in Words:']\n- Location: Near the numerical amount.\n- Content: The full textual representation of the number and currency (e.g., 'US Dollars One Hundred Thousand Only')."},
            {"name": "FB CHARGES", "description": "Objective: Determine who bears Foreign Bank charges.\n- Options: 'on us'/'OUR' vs 'on beneficiary'/'BEN'.\n- Logic: If one option is struck out, choose the other. Else, look for a positive mark (✓, X). If neither, default is 'on us'.\n- Format: Map 'on us'/'OUR' to 'U'. Map 'on beneficiary'/'BEN' to 'O'."},
            {"name": "TRANSACTION Product Code Selection", "description": "Objective: Extract the internal bank product code or transaction type selected.\n- Labels: ['Product Code:', 'Transaction Product:']\n- Content: Often an alphanumeric code or a selection from a list (e.g., 'Import Advance Payment')."},
            {"name": "TRANSACTION EVENT", "description": "Objective: Describe the event initiated by the document.\n- Content: Inferred from the document's purpose. For a CRL, this is typically 'Payment Instruction' or 'Remittance Request'."},
            {"name": "VALUE DATE", "description": "Objective: Extract the requested effective date for the transaction.\n- Labels: ['Value Date:', 'Requested Settlement Date:', 'Debit Date:']\n- Format: 'DD-MM-YYYY', or a term like 'Spot'."},
            {"name": "EXCHANGE RATE", "description": "Objective: Extract the specified exchange rate for the transaction, if any.\n- Labels: ['Exchange Rate:', 'FX Rate:', 'Conversion Rate:']\n- Content: Can be a number or an equation (e.g., '1 USD = 83.50 INR')."},
            {"name": "TREASURY REFERENCE NO", "description": "Objective: Extract a Treasury Reference or Forex Deal ID, if specified.\n- Labels: ['Treasury Ref No:', 'Forex Deal ID:', 'FX Contract No.:']\n- Location: In sections related to exchange rates or specific bank instructions."},
            {"name": "MODE OF REMITTANCE", "description": "Objective: Extract the payment method.\n- Labels: ['Mode of Payment:', 'Payment Method:', 'Remit by:']\n- Content: Common values are 'SWIFT Transfer', 'Telegraphic Transfer (TT)', 'Wire Transfer'."},
            {"name": "SPECIFIC REFERENCE FOR SWIFT FIELD 70/72", "description": "Objective: Extract narrative or instructions for SWIFT fields 70/72.\n- Labels: ['Payment Reference (for SWIFT F70):', 'Message to Beneficiary Bank (F72):', 'Special Ref No to be mentioned in Swift']\n- Content: Free-form text like invoice numbers, PO numbers, or payment purpose."},
        ],
        "GoodsAndShippingInfo": [
            {"name": "DESCRIPTION OF GOODS", "description": "Objective: Extract the detailed description of goods or services being paid for.\n- Labels: ['Description of Goods/Services:', 'Details of Import:', 'Particulars:']\n- Note: This should be a specific, detailed account, not a general classification."},
            {"name": "TYPE OF GOODS", "description": "Objective: Classify goods as 'Raw Material' or 'Capital Goods'.\n- Location: Find the sentence '...import of ... as part of our Raw Material/Capital Goods requirements'.\n- Logic: If one option is struck through, choose the other. If no strikethrough, look for a positive mark (✓, X, *). If neither, default to 'Raw Material'."},
            {"name": "INVOICE NO", "description": "Objective: Extract the invoice number referenced within the CRL.\n- Labels: ['Invoice No.:', 'Ref. Invoice:', 'PI No.:']\n- Location: In the body of the CRL, often in payment purpose or shipping details sections.\n- Format: Return as a string, removing hyphens '-' but preserving other special characters."},
            {"name": "INVOICE DATE", "description": "Objective: Extract the date of the invoice referenced in the CRL.\n- Labels: ['Invoice Date:', 'Date of Invoice:', 'PI Date:']\n- Location: Near the referenced Invoice Number within the CRL.\n- Format: 'DD-MM-YYYY'."},
            {"name": "INVOICE VALUE", "description": "Objective: Extract the value of the invoice referenced in the CRL.\n- Labels: ['Invoice Amount:', 'Invoice Value:']\n- Location: Near the referenced Invoice Number within the CRL.\n- Note: Extract numerical value only."},
            {"name": "HS CODE", "description": "Objective: Extract the Harmonized System (HS/HSN) code for the goods.\n- Labels: ['HS Code:', 'HSN Code:', 'Tariff Code:']\n- Location: Near the 'Description of Goods'.\n- Format: 6-10 digit number, sometimes with periods. Extract digits only (e.g., '8517.62.00' -> '85176200'). If multiple, separate with a comma."},
            {"name": "LATEST SHIPMENT DATE", "description": "Objective: Extract the latest date goods must be shipped.\n- Labels: ['Latest Shipment Date:', 'Shipment by:', 'LSD:']\n- Location: In shipping terms or Letter of Credit conditions.\n- Format: 'DD-MM-YYYY'."},
            {"name": "DISPATCH PORT", "description": "Objective: Extract the port of loading/dispatch.\n- Labels: ['Port of Despatch:', 'Port of Loading:', 'From Port:', 'Shipped From:']\n- Content: A geographical location name (e.g., 'Port of Hamburg', 'Qingdao')."},
            {"name": "DELIVERY PORT", "description": "Objective: Extract the port of discharge/delivery.\n- Labels: ['Port of Delivery:', 'Port of Discharge:', 'To Port:', 'Destination Port:']\n- Content: A geographical location name (e.g., 'Port of New York', 'Nhava Sheva Port')."},
            {"name": "INCO TERM", "description": "Objective: Extract the three-letter Incoterm and associated location.\n- Labels: ['Incoterm:', 'Trade Term:', 'Delivery Term:']\n- Format: A three-letter code followed by a place (e.g., 'FOB Shanghai', 'EXW Seller's Factory')."},
            {"name": "COUNTRY OF ORIGIN", "description": "Objective: Extract the country where goods were manufactured.\n- Labels: ['Country of Origin:', 'Origin of Goods:', 'Made in:']\n- Note: Refers to goods' origin, not beneficiary's or applicant's country."},
            {"name": "IMPORT LICENSE DETAILS", "description": "Objective: Extract details of any import license or permit.\n- Labels: ['Import Licence No.:', 'Permit Number:', 'Authorization Details:']\n- Content: Can be a license number, validity dates, or issuing authority."},
            {"name": "THIRD PARTY EXPORTER NAME", "description": "Objective: Extract name of a third-party exporter if they are not the main beneficiary.\n- Labels: ['Third Party Exporter:', 'Actual Exporter (if different from Beneficiary):']\n- Note: Only extract if this entity is explicitly mentioned as being different from the seller/beneficiary."},
            {"name": "THIRD PARTY EXPORTER COUNTRY", "description": "Objective: Extract the country of the third-party exporter, if specified.\n- Location: Near the third-party exporter's name or as part of their address."},
        ],
        "Declarations": [
            {"name": "STANDARD DECLARATIONS AS PER PRODUCTS", "description": "Objective: Extract all standard declarations, undertakings, or legal statements made by the applicant.\n- Section Headers: ['Declarations:', 'Undertakings:', 'Applicant's Declaration:']\n- Location: Often in numbered/bulleted lists or paragraphs before the signature.\n- Keywords: 'I/We declare', 'We confirm', 'We undertake', 'As per FEMA guidelines'.\n- Note: Capture the full and complete text of all such clauses."},
        ]
    },
    "INVOICE": {
        "AllFields": [
            {"name": "TYPE OF INVOICE - COMMERCIAL/PROFORMA/CUSTOMS", "description": "Objective: Identify the invoice type.\n- Keywords: Look for prominent titles like 'COMMERCIAL INVOICE', 'PROFORMA INVOICE', 'TAX INVOICE', 'CUSTOMS INVOICE'.\n- Note: 'Order Confirmation' or 'Sales Order' can function as a Proforma Invoice."},
            {"name": "INVOICE DATE", "description": "Objective: Extract the date the invoice was issued.\n- Labels: ['Invoice Date', 'Date', 'Issue Date']\n- Location: Typically in the header, near the Invoice No."},
            {"name": "INVOICE NO", "description": "Objective: Extract the unique invoice identifier.\n- Labels: ['Invoice No.', 'Invoice #', 'Inv. No.', 'PROFORMA NO:']\n- Location: Prominently in the header."},
            {"name": "BUYER NAME", "description": "Objective: Extract the full name of the buyer/customer.\n- Labels: ['CONSIGNEE:', 'Buyer:', 'Bill To:', 'Customer:', 'Sold To:', 'Importer:']\n- Location: The primary name in the recipient's detail block."},
            {"name": "BUYER ADDRESS", "description": "Objective: Extract the buyer's complete mailing address.\n- Location: Under labels like 'CONSIGNEE:' or 'Bill To:'.\n- Note: Do not include the buyer's name in the address string."},
            {"name": "BUYER COUNTRY", "description": "Objective: Extract the buyer's country and provide its 2-letter ISO code.\n- Location: Usually the last part of the buyer's address.\n- Action: Identify country name (e.g., 'India'), then convert to ISO 3166-1 alpha-2 code ('IN')."},
            {"name": "SELLER NAME", "description": "Objective: Extract the full legal name of the seller/issuer.\n- Labels: ['Seller', 'From', 'Exporter', 'Beneficiary']\n- Location: Prominently in the invoice header or letterhead."},
            {"name": "SELLER ADDRESS", "description": "Objective: Extract the seller's complete mailing address.\n- Location: Near the seller's name in the header or footer."},
            {"name": "SELLER COUNTRY", "description": "Objective: Extract the seller's country.\n- Location: Typically the last component of the seller's address."},
            {"name": "INVOICE CURRENCY", "description": "Objective: Extract the 3-letter ISO 4217 currency code.\n- Location: Next to monetary values or in table headers (e.g., 'Amount USD').\n- Note: Prioritize codes (USD, EUR) over symbols ($)."},
            {"name": "INVOICE AMOUNT/VALUE", "description": "Objective: Extract the primary total value of goods/services, often a subtotal or net amount.\n- Labels: ['Total', 'Subtotal', 'Net Amount', 'Invoice Total']\n- Note: Extract numerical value only."},
            {"name": "INVOICE AMOUNT/VALUE IN WORDS", "description": "Objective: Extract the total amount written in words.\n- Labels: ['Amount in Words', 'Say Total', 'In Words']\n- Note: Capture the full text, including currency name and suffixes like 'Only'. Return null if not present."},
            {"name": "BENEFICIARY ACCOUNT NO / IBAN", "description": "Objective: Extract the beneficiary's International Bank Account Number (IBAN).\n- Labels: Look specifically for 'IBAN'.\n- Content: A string starting with a 2-letter country code.\n- Note: If no IBAN is explicitly found, return null."},
            {"name": "BENEFICIARY BANK", "description": "Objective: Extract the beneficiary's bank name.\n- Labels: ['Beneficiary Bank', 'Bank Name', 'Banca d'Appoggio']\n- Location: In the 'Bank Details' or 'Payment Instructions' section."},
            {"name": "BENEFICIARY BANK ADDRESS", "description": "Objective: Extract the beneficiary bank's full address.\n- Location: Near the bank's name in the payment details section."},
            {"name": "BENEFICIARY BANK SWIFT CODE / SORT CODE/ BSB / IFS CODE", "description": "Objective: Extract the beneficiary bank's 11-char SWIFT/BIC code.\n- Primary Target (SWIFT): Look for 'SWIFT Code:', 'BIC Code:'.\n- Normalization: If 8 chars, append 'XXX'.\n- Fallback: If no SWIFT, look for other bank identifiers like IFSC, Sort Code, etc.\n- Output: Return the normalized 11-char SWIFT code or the first valid fallback."},
            {"name": "Total Invoice Amount", "description": "Objective: Extract the final, definitive total amount due.\n- Labels: ['Grand Total', 'Total Amount Due', 'Total Invoice Value', 'Totale Fattura']\n- Note: This is the ultimate figure to be paid, inclusive of all charges/taxes if listed as such. Extract numerical value only."},
            {"name": "Invoice Amount", "description": "Objective: Extract the primary invoice amount. Often synonymous with 'Total Invoice Amount'.\n- Note: On simple invoices, this is the grand total. On complex ones, it could be a subtotal before final fees."},
            {"name": "Beneficiary Name", "description": "Objective: Extract the name of the payment recipient. Usually the same as 'SELLER NAME'.\n- Labels: ['Beneficiary', 'Payable to']\n- Location: In 'Bank Details' or inferred from the seller's identity."},
            {"name": "Beneficiary Address", "description": "Objective: Extract the beneficiary's full mailing address. Usually the same as 'SELLER ADDRESS'."},
            {"name": "DESCRIPTION OF GOODS", "description": "Objective: Extract the detailed descriptions of all products/services.\n- Location: Within the main table of line items under headers like 'Description' or 'Item Description'.\n- Note: Combine descriptions from all line items into a single string, separated by a newline."},
            {"name": "QUANTITY OF GOODS", "description": "Objective: Extract the quantity for each line item, including units.\n- Location: In the line item table under headers like 'Quantity', 'Qty', 'Units', 'U.M.'.\n- Format: Combine quantities into a single string, separated by a semicolon (e.g., '2 PC; 10 EA; 1 KG')."},
            {"name": "PAYMENT TERMS", "description": "Objective: Extract the payment conditions.\n- Labels: ['Payment Terms', 'Terms', 'Condizioni pagamento']\n- Content: Can include timeframe ('Net 30'), percentage due ('100% advanced'), or method."},
            {"name": "BENEFICIARY/SELLER'S SIGNATURE", "description": "Objective: Identify the seller's signature or authorization.\n- Location: At the bottom of the invoice in a signature block.\n- What to Extract: A typed name if present, otherwise 'Signature present' for a handwritten one. Return null if absent."},
            {"name": "APPLICANT/BUYER'S SIGNATURE", "description": "Objective: Identify the buyer's signature or acceptance, if present.\n- Location: A signature block labeled 'Accepted By' or similar. Less common on invoices.\n- Note: Return null if absent."},
            {"name": "MODE OF REMITTANCE", "description": "Objective: Extract the payment method.\n- Labels: ['Payment Method', 'Mode of Payment', 'Mod, pagamento']\n- Content: Examples: 'Wire Transfer', 'Bank Transfer'."},
            {"name": "MODE OF TRANSIT", "description": "Objective: Extract the method of transportation for the goods.\n- Labels: ['Ship Via', 'Mode of Shipment', 'Transport Mode', 'Carrier']\n- Content: Examples: 'Sea', 'Air', 'Road', 'Ocean'. Return null if not specified."},
            {"name": "INCO TERM", "description": "Objective: Extract the Incoterm and its named place.\n- Labels: ['Incoterms', 'Terms of Sale', 'Resa merce']\n- Format: Three-letter code plus location (e.g., 'EXW Scarperia', 'FOB Shanghai Port')."},
            {"name": "HS CODE", "description": "Objective: Extract the Harmonized System (HS/HTS) code for products.\n- Labels: ['HS Code', 'HTS Code', 'Tariff Code']\n- Location: In the line item details. If multiple, separate with a semicolon. Return null if absent."},
            {"name": "Intermediary Bank (Field 56)", "description": "Objective: Extract details of any intermediary/correspondent bank, if specified.\n- Labels: ['Intermediary Bank', 'Correspondent Bank', 'Field 56']\n- Note: This is an additional bank used for routing payment. Return null if not mentioned."},
            {"name": "INTERMEDIARY BANK NAME", "description": "Objective: Extract the name of the intermediary bank, if specified.\n- Note: Must be explicitly labeled as intermediary/correspondent."},
            {"name": "INTERMEDIARY BANK ADDRESS", "description": "Objective: Extract the address of the intermediary bank, if specified."},
            {"name": "INTERMEDIARY BANK COUNTRY", "description": "Objective: Extract the country of the intermediary bank, if specified."},
            {"name": "Party Name ( Applicant )", "description": "Objective: Extract the applicant's name, which is the buyer/customer.\n- Labels: ['Bill To:', 'Customer:', 'Buyer:', 'Applicant:']"},
            {"name": "Party Name ( Beneficiary )", "description": "Objective: Extract the beneficiary's name, which is the seller/exporter."},
            {"name": "Party Country ( Beneficiary )", "description": "Objective: Extract the beneficiary's country from their main address."},
            {"name": "Party Type ( Beneficiary Bank )", "description": "Objective: Identify the role of the beneficiary's bank. Usually inferred as 'Beneficiary Bank'."},
            {"name": "Party Name ( Beneficiary Bank )", "description": "Objective: Extract the name of the bank holding the beneficiary's account."},
            {"name": "Party Country ( Beneficiary Bank )", "description": "Objective: Extract the beneficiary bank's country. Can be inferred from the IBAN's 2-letter prefix (e.g., 'IT' -> Italy)."},
            {"name": "Drawee Address", "description": "Objective: Extract the name and address of the drawee.\n- Note: If no specific drawee is named (for a bill of exchange), this defaults to the buyer's name and address."},
            {"name": "PORT OF LOADING", "description": "Objective: Extract the port or place where goods are loaded for export.\n- Labels: ['Port of Loading', 'POL', 'From Port', 'Place of Loading']\n- Note: For 'EXW' Incoterms, this is the seller's premises."},
            {"name": "PORT OF DISCHARGE", "description": "Objective: Extract the port or place where goods are unloaded in the destination country.\n- Labels: ['Port of Discharge', 'POD', 'To Port', 'Final Destination']\n- Note: May not be present on proforma invoices. Return null if not specified."},
            {"name": "VESSEL TYPE", "description": "Objective: Extract the type of transport used.\n- Examples: 'Vessel', 'Aircraft', 'Truck'.\n- Note: Can be inferred from 'Mode of Transit'. Return null if not specified."},
            {"name": "VESSEL NAME", "description": "Objective: Extract the specific name of the ship, flight number, or voyage number.\n- Labels: ['Vessel Name', 'Voyage No.', 'Flight No.']\n- Note: Return null if not specified."},
            {"name": "THIRD PARTY EXPORTER NAME", "description": "Objective: Extract the name of a third-party exporter, if they are explicitly named and are different from the seller.\n- Note: Return null if not applicable."},
            {"name": "THIRD PARTY EXPORTER COUNTRY", "description": "Objective: Extract the country of the third-party exporter, if one is named.\n- Note: Return null if not applicable."}
        ]
    }
}
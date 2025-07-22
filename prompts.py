CLASSIFICATION_PROMPT_TEMPLATE = """
**Task:** You are an AI Document Classification Specialist. Your objective is to meticulously analyze the provided document pages ({num_pages} pages) and accurately classify the document's primary type based on its intrinsic purpose, structural characteristics, and specific content elements. The document may consist of multiple pages that collectively form a single logical entity.

**Acceptable Document Types:**
{acceptable_types_str}
Strictly classify the document ONLY amongst the acceptable document types.

**Detailed Instructions for Classification:**

1.  **Holistic Review:** Conduct a comprehensive examination of all pages. Pay close attention to titles, headings, recurring phrases, specific keywords (see below), data tables (e.g., itemized goods, payment details), and the overall layout to discern the document's fundamental function.
2.  **Content and Keyword Analysis (Prioritize explicit titles and document structure):**
    * **INVOICE (Commercial, Proforma, Customs):**
        * **Primary Keywords/Titles:** Search for explicit titles like "Invoice", "Commercial Invoice", "Proforma Invoice", "Tax Invoice", "Customs Invoice", "Proforma", "PI".
        * **Supporting Keywords/Phrases:** "Fattura" (Italian), "Rechnung" (German), "Facture" (French), "Bill", "Statement of Charges". Documents titled "Order Confirmation", "Sales Contract", "Sales Order", "Sales Agreement", "Indent", "PO", "Purchase Order" can function as a **Proforma Invoice** if they provide full itemization, pricing, terms, and are used to initiate payment or L/C.
        * **Core Structural Elements:**
            * A unique "Invoice Number" or "Reference Number".
            * Clear identification of "Seller" (or "Shipper", "Exporter", "Beneficiary", "From") and "Buyer" (or "Consignee", "Importer", "Bill To", "To") with names and addresses.
            * Itemized list of goods or services: descriptions, quantities, unit prices, line totals.
            * A "Total Amount Due", "Grand Total", or similar aggregate financial sum.
            * An "Invoice Date" or "Date of Issue" (a Proforma might use an "Order Date" or "Proforma Date").
            * Payment terms (e.g., "Net 30", "Advance Payment") and often bank details for payment.
        * **Differentiation:**
            * **Commercial Invoice:** Typically a definitive bill for goods already shipped or services rendered; requests payment for a completed transaction part.
            * **Proforma Invoice:** A preliminary quotation or bill issued *before* goods shipment or service completion. Used for buyer to arrange financing (like L/C), make a prepayment, or for customs pre-clearance. Often explicitly titled "Proforma Invoice".
            * **Customs Invoice:** Specifically formatted for customs authorities, detailing goods for import/export, including values, HS codes, country of origin, package details, for duty assessment.
    * **CRL (Customer Request Letter) / Application:**
        * **Primary Keywords/Titles:** "Request Letter", "Application for [Bank Product/Service]", "Letter of Instruction", "Remittance Application", "Import Payment Request".
        * **Supporting Keywords/Phrases:** Addressed "To The Manager, [Bank Name]", phrases like "We request you to...", "Kindly process the remittance for...", "Please debit our account...", "Letter of Undertaking".
        * **Content Focus:** Formal, written instruction from a customer (Applicant) to their bank. Explicitly requests the bank to perform a financial transaction (e.g., "issue a Letter of Credit", "remit funds for import", "process an outward remittance", "make an advance payment"). Contains details of the transaction: amount, currency, purpose, beneficiary name and bank details. Applicant's account to be debited is usually specified. Often includes declarations and signature of the applicant.
        * **Parties:** Clearly identifies an "Applicant" (customer) and a "Beneficiary" (recipient of funds).
3.  **Primary Purpose Determination:** Based on the collective evidence from all pages (explicit titles being a strong indicator), the presence/absence of key fields, and the characteristic markers outlined above, ascertain which single "Acceptable Document Type" most accurately represents the *overall primary purpose* of the document. What is the document's core function or the action it is intended to facilitate?
4.  **Confidence Assessment:** Assign a confidence score based on the clarity and preponderance of evidence.
    * **High Confidence (0.90-1.00):** An explicit, unambiguous title matching an acceptable type (e.g., "COMMERCIAL INVOICE") AND the presence of most core fields/structural elements characteristic of that type. The document's purpose is very clear.
    * **Medium Confidence (0.70-0.89):** The title might be generic (e.g., just "INVOICE" where it could be Commercial or Proforma) or the type is inferred (e.g., a Purchase Order acting as a Proforma Invoice based on its content). Core fields and structure strongly suggest a particular type, but some ambiguity or deviation exists. Or, a clear title but some expected key elements are missing or unclear.
    * **Low Confidence (0.50-0.69):** Title is ambiguous, misleading, or absent. Content could align with multiple types, or is missing several key indicators for any single type, making classification difficult.
    * **Very Low/Unknown (0.0-0.49):** Document does not appear to match any of the acceptable types based on available indicators, or is too fragmented/illegible for reliable classification.
5.  **Output Format (Strict Adherence Required):**
    * Return ONLY a single, valid JSON object.
    * The JSON object must contain exactly three keys: `"classified_type"`, `"confidence"`, and `"reasoning"`.
    * `"classified_type"`: The determined document type string. This MUST be one of the "Acceptable Document Types". If, after thorough analysis, the document does not definitively match any acceptable type based on the provided indicators, use "UNKNOWN".
    * `"confidence"`: A numerical score between 0.0 and 1.0 (e.g., 0.95).
    * `"reasoning"`: A concise but specific explanation for your classification. Reference explicit titles, key terms found (or absent), presence/absence of core fields, or structural elements that led to your decision (e.g., "Document explicitly titled 'PROFORMA INVOICE' on page 1. Contains seller/buyer, itemized goods with prices, total value, and payment terms. Serves as a preliminary bill for payment initiation."). If 'UNKNOWN', explain why (e.g., "Lacks clear title and key invoice fields like invoice number or distinct buyer/seller sections. Appears to be an internal statement not matching defined types.").

**Example Output:**
```json
{{
  "classified_type": "INVOICE",
  "confidence": 0.98,
  "reasoning": "Document exhibits all core characteristics of a proforma invoice: details seller and buyer, lists specific goods with quantities and unit prices leading to a total amount, specifies payment terms ('50% advance...'), and indicates 'Ship Date TBD'. While not explicitly titled 'Proforma Invoice', its structure and content align perfectly with its function as a preliminary bill for initiating payment, akin to a sales order formatted for external use."
}}

Important: Your response must be ONLY the valid JSON object. No greetings, apologies, or any text outside the JSON structure.
"""

EXTRACTION_PROMPT_TEMPLATE = """
**Your Role:** You are an highly meticulous, accurate and elite AI Document Analysis Specialist, functioning as a digital subject matter expert. Your primary function is to deconstruct and interpret business documents with supreme accuracy. You are expected to go beyond simple text recognition, applying contextual understanding and critical thinking to extract structured data precisely as instructed. Your outputs must be verifiable, auditable, and reflect a deep understanding of the document's structure and intent.

**Task:** Analyze the provided {num_pages} pages, which together constitute a single logical '{doc_type}' document associated with Case ID '{case_id}'. Carefully extract the specific data fields listed below. Use the provided detailed descriptions to understand the context, meaning, typical location, expected format, and potential variations of each field within this document type. Consider all pages to find the most relevant and accurate information. Pay close attention to nuanced instructions, including differentiation between similar concepts and rules for inference or default values if specified.
For each field, you must use the detailed `description` to understand its specific context, meaning, typical location, expected format, and potential variations within this document type. Information may be spread across multiple pages; you must synthesize all available information to find the most accurate and complete value for each field. Pay meticulous attention to nuanced instructions, including rules for differentiating between similar concepts (e.g., 'Applicant' vs. 'Beneficiary'), and apply rules for inference or default values only when explicitly permitted by the field's description.

**Fields to Extract (Name and Detailed Description):**
{field_list_str}


**Output Requirements (Strict):**

1.  **JSON Only:** You MUST return ONLY a single, valid JSON object as your response. This is a strict machine-to-machine interface; do not include any introductory text, explanations, summaries, apologies, or any other text outside of the JSON structure. Your response must begin directly with `{{` and end with `}}` to ensure seamless programmatic integration.
2.  **JSON Structure:** The JSON object MUST have keys that correspond EXACTLY to the field **names** provided in the "Fields to Extract" list. **Every single requested field must be included as a key in the output to ensure a complete and predictable structure.** Your response MUST be a perfectly valid JSON, free of any extra quotes, trailing commas, or special characters that would cause a parser to fail.STRICTLY MAKE SURE IT IS A VALID JSON WITH NO EXTRA QUOTES, COMMAS, SPECIAL CHARACTERS ETC. AND CAN BE PARSED PROGRAMATICALLY BY A PARSER.
3.  **Field Value Object:** Each value associated with a field key MUST be another JSON object containing the following three keys EXACTLY:
    * `"value"`: The extracted text value for the field.
        * If the field is clearly present, extract the value with absolute precision, ensuring every character is accurately represented and free of extraneous text/formatting (unless the formatting is part of the value, like a specific date format if ISO conversion is not possible).
        * If the field is **not found** or **not applicable** after thoroughly searching all pages and considering contextual clues as per the field description, use the JSON value `null` (not the string "null").
        * If multiple potential values exist (e.g., different addresses for a seller), select the one most pertinent to the field's specific context (e.g., 'Seller Address' for invoice issuance vs. 'Seller Corporate HQ Address' if the field specifically asks for that). Document ambiguity in reasoning.
        * For amounts, extract numerical values (e.g., "15000.75", removing currency symbols or group separators like commas unless they are part of a regional decimal format that must be preserved). Currency is typically a separate field.
        * For dates, if possible and certain, convert to ISO 8601 format (YYYY-MM-DD). If conversion is uncertain due to ambiguous source format (e.g., "01/02/03"), extract as it appears and note the ambiguity and original format in the reasoning.
        * For multi-line addresses, concatenate lines into a single string, typically separated by a comma and space (e.g., "123 Main St, Anytown, ST 12345, Country").

    * `"confidence"`: **Granular Character-Informed, Contextual, and Source-Aware Confidence Score (Strict)**
        * **Core Principle:** The overall confidence score (float, 0.00 to 1.00, recommend 2 decimal places) for each field MUST reflect the system's certainty about **every single character** of the extracted value, AND the **contextual correctness and verifiability** of that extraction. It's a holistic measure.
        * **Key Factors Influencing Confidence:**
            1.  **OCR Character Quality & Ambiguity:** Clarity and sharpness of each character (machine-print vs. handwriting). Low confidence for ambiguous characters (e.g., '0'/'O', '1'/'l'/'I', '5'/'S') unless context makes it near-certain.
            2.  **Handwriting Legibility:** Clarity, consistency, and formation of handwritten characters.
            3.  **Field Format Adherence:** How well the extracted value matches the expected data type and pattern (e.g., all digits for an account number, valid date structure, correct SWIFT code pattern). Deviations drastically lower confidence.
            4.  **Label Presence & Quality:** Was the value found next to a clear, standard, unambiguous label matching the field description? (e.g., "Invoice No.:" vs. inferring from a poorly labeled column). Explicit, standard labels lead to higher confidence.
            5.  **Positional Predictability:** Was the field found in a common, expected location for that document type versus an unusual one?
            6.  **Contextual Plausibility & Consistency:** Does the value make sense for the field and in relation to other extracted fields? (e.g., a 'Latest Shipment Date' should not be before an 'Order Date'). Cross-validation (e.g., amount in words vs. numeric amount) consistency is key.
            7.  **Completeness of Information:** If a field expects multiple components (e.g., full address) and parts are missing/illegible, this reduces confidence for the entire field.
            8.  **Source Document Quality:** Overall document clarity, scan quality, skew, rotation, background noise, stamps/markings obscuring text.
            9.  **Inference Level:** Was the value directly extracted or inferred? Higher degrees of inference lower confidence.

        * **Confidence Benchmarks (Stricter & More Granular):**
            * **0.99 - 1.00 (Very High/Near Certain):** Reserved for perfect, All characters perfectly clear, machine-printed text next to an explicit, standard label in a predictable location. Perfect format match. Contextually validated and sound. No plausible alternative interpretation. (Example: A clearly printed Invoice Number next to "Invoice No.:" label).
            * **0.95 - 0.98 (High):** Characters very clear and legible (excellent machine print or exceptionally neat handwriting). Minor, non-ambiguity-inducing visual imperfections. Strong label or unmistakable positional/contextual evidence. Correct format. Contextually valid. (Example: A clearly printed total amount next to "Grand Total:").
            * **0.88 - 0.94 (Good):** Generally clear, but minor, identifiable factors prevent higher scores:
                * One or two characters with slight ambiguity resolved with high confidence by context or pattern.
                * Very clean, legible, and consistent handwriting.
                * Information reliably extracted from structured tables with clear headers.
                * Minor print defects (slight fading/smudging) not obscuring character identity.
            * **0.75 - 0.87 (Moderate):** Value is legible and likely correct, but there are noticeable issues affecting certainty for some characters/segments, or some level of inference was required:
                * Moderately clear handwriting with some variability or less common letter forms.
                * Slightly blurry, pixelated, or faded print requiring careful interpretation for several characters.
                * Value inferred from contextual clues or non-standard labels with reasonable, but not absolute, certainty. (e.g., identifying a "Beneficiary Bank" from a block of payment text without an explicit label).
            * **0.60 - 0.74 (Low):** Significant uncertainty. Parts of the value are an educated guess, or the source is challenging:
                * Poor print quality (significant fading, widespread smudging, pixelation) affecting key characters.
                * Difficult or messy handwriting for a substantial portion of the value.
                * High ambiguity for several characters or critical segments where context provides only weak support. Value inferred with significant assumptions or from unclear/damaged source text.
            * **< 0.60 (Very Low / Unreliable):** Extraction is highly speculative or impossible to perform reliably. Value likely incorrect, incomplete, or based on guesswork. Text is largely illegible, critical characters are indecipherable, or contextual validation fails insurmountably.
        * If `"value"` is `null`, `None` and `nan` (field not found/applicable), `"confidence"` MUST be `0.0`.

    * `"reasoning"`: A concise but specific explanation justifying the extracted `value` and the assigned `confidence` score. This is crucial for auditability and improvement.
        * Specify *how* the information was identified (e.g., "Directly beside explicit label 'Invoice No.' on page 1.", "Inferred from the 'BILL TO:' address block on page 2 as buyer's name.", "Calculated sum of all line item totals from table on page 3.").
        * Indicate *where* it was found (e.g., "Page 1, top right section.", "Page 3, under table column 'Description'.", "Page 5, section titled 'Payment Instructions'.").
        * **Mandatory for any confidence score below 0.99:** Briefly explain the *primary factors* leading to the reduced confidence. Reference specific issues:
            * Character ambiguity: "Value is 'INV-O012B'; Confidence 0.78: Second char 'O' could be '0', last char 'B' could be '8'; document slightly blurred in this area."
            * Print/Scan Quality: "Value '123 Main Street'; Confidence 0.85: Slight fading on 'Street', making 'S' and 't' less than perfectly sharp."
            * Handwriting: "Value 'Johnathan Doe'; Confidence 0.70: First name legible but 'Johnathan' has an unclear 'h' and 'n'; 'Doe' is clear."
            * Inference/Labeling: "Value 'Global Exporters Inc.'; Confidence 0.90: Inferred as Seller Name from prominent placement in header, no explicit 'Seller:' label."
            * Formatting Issues: "Value '15/07/2024'; Confidence 0.92: Date format DD/MM/YYYY clearly extracted; slight ink bleed around numbers."
            * Contextual Conflict: "Value for 'Net Weight' is '1500 KG', but 'Gross Weight' is '1400 KG'; Confidence 0.60 for Net Weight due to inconsistency requiring review."
        * If confidence is 0.99-1.00, reasoning can be succinct, e.g., "All characters perfectly clear, machine-printed, explicit standard label, contextually validated."
        * If `"value"` is `null`, briefly explain *why* (e.g., "No field labeled 'HS Code' or any recognizable tariff code found on any page.", "The section for 'Intermediary Bank Details' was present but explicitly marked 'Not Applicable'.").

**Example of Expected JSON Output Structure (Reflecting Stricter Confidence & Generic Reasoning):**
(Note: Actual field names will match those provided in the 'Fields to Extract' list for the specific '{doc_type}')

```json
{{
  "INVOICE_NO": {{
    "value": "INV-XYZ-789",
    "confidence": 0.99,
    "reasoning": "Extracted from explicit label 'Invoice #:' on page 1, header. All characters are machine-printed, clear, and unambiguous. Format matches typical invoice numbering."
  }},
  "BUYER_NAME": {{
    "value": "Generic Trading Co.",
    "confidence": 1.00,
    "reasoning": "Extracted from 'BILL TO:' section, page 1. All characters perfectly clear, machine-printed, standard label, contextually validated."
  }},
  "HS_CODE": {{
    "value": null,
    "confidence": 0.0,
    "reasoning": "No field labeled 'HS Code', 'HTS Code', or 'Tariff Code', nor any recognizable HS code pattern, found on any page of the document."
  }},
  "PAYMENT_TERMS": {{
    "value": "Net 30 days from date of invoice",
    "confidence": 0.98,
    "reasoning": "Extracted from section labeled 'Payment Terms:' on page 2. Text is clearly printed and directly associated with a standard label. All characters legible."
  }},
  "DATE_AND_TIME_OF_RECEIPT_OF_DOCUMENT": {{
    "value": "2024-07-16 11:25",
    "confidence": 0.90,
    "reasoning": "Date '16 JUL 2024' clearly visible in a bank's 'RECEIVED' stamp on page 1. Time '11:25' also part of the stamp, clearly printed. Converted date to ISO format. Confidence slightly below max due to typical minor imperfections in stamp quality."
  }}
  // ... (all other requested fields for the '{doc_type}' document would follow this structure)
}}

Important: Your response must be ONLY the valid JSON object. No greetings, apologies, or any text outside the JSON structure.
"""
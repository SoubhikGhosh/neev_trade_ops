# prompts.py

CORRECTION_PROMPT_TEMPLATE = """
**Your Role:** You are a JSON Correction Specialist AI. Your task is to fix a flawed response from another AI.

**Context:** An initial attempt was made to extract structured data from a '{doc_type}' document for Case ID '{case_id}'. That attempt failed to produce a valid, structured JSON output according to the required schema.

**The flawed, unstructured output from the previous AI was:**
{failed_output}


**Your Task:**
1.  **Analyze the flawed output.** It may contain partially correct data, explanations, or refusals.
2.  **Re-examine the original document** (provided as context) and the **Original Extraction Requirements** listed below.
3.  **Produce a valid JSON object** that strictly adheres to the required schema and accurately reflects the data in the document.
4.  If the flawed output is helpful, use it to guide your extraction. If it is useless (e.g., an error message), ignore it and perform the extraction from scratch based on the original document and requirements.
5.  **You MUST follow all rules from the original extraction prompt**, including the detailed instructions for creating `_Value`, `_Confidence`, and `_Reasoning` keys for every field.

---
**Original Extraction Requirements:**
{field_list_str}
"""

CLASSIFICATION_PROMPT_TEMPLATE = """
**Task:** You are an AI Document Analysis Specialist. Your objective is to provide both a
high-level summary and a detailed, accurate technical classification for the provided document
({num_pages} pages).

---
**Part 1: High-Level Summary**
Provide a value for the following fields:
- `image_description`: A one-sentence summary of the document's main purpose, including
  key entities and values.
- `image_type`: A general, human-readable classification (e.g., "Request Letter",
  "Proforma Invoice").

---
**Part 2: Detailed Technical Classification**
Provide a value for the following fields based on a meticulous analysis:
- `classified_type`: Strictly classify the document as ONE of the following types:
  {acceptable_types_str}, or "UNKNOWN".
- `confidence`: Assign a confidence score for your `classified_type` decision based on
  the rubric below.
- `reasoning`: A concise but specific explanation for your `classified_type` decision,
  referencing key evidence.

**Detailed Instructions for `classified_type` Determination:**

1.  **Holistic Review:** Examine all pages for titles, headings, keywords, data tables,
    and layout to discern the document's fundamental function.
2.  **Content and Keyword Analysis:**
    * **INVOICE (Commercial, Proforma, Customs):**
        * **Titles:** "Invoice", "Commercial Invoice", "Proforma Invoice", "Tax Invoice",
          "Proforma", "PI".
        * **Functionality:** Documents like "Order Confirmation", "Sales Contract", or
          "Purchase Order" should be classified as `INVOICE` if they provide full
          itemization, pricing, and terms.
        * **Structure:** Must contain a unique "Invoice Number", "Seller", "Buyer", an
          itemized list of goods/services with a "Total Amount", and an "Invoice Date".
    * **CRL (Customer Request Letter):**
        * **Titles:** "Request Letter", "Application for...", "Letter of Instruction",
          "Remittance Application".
        * **Content:** A formal instruction from a customer ("Applicant") to their bank.
          It explicitly requests a financial transaction (e.g., "process the remittance,"
          "debit our account") and provides details for a "Beneficiary."

**Confidence Score Rubric (for the `confidence` field):**
- **0.90 - 1.00 (High):** An explicit title (e.g., "PROFORMA INVOICE") and all core
  structural elements are present.
- **0.70 - 0.89 (Medium):** A generic title (e.g., "INVOICE") or the type is inferred
  (e.g., a PO acting as an Invoice). Structure is strong but may have minor ambiguity.
- **0.50 - 0.69 (Low):** Title is absent or ambiguous. Content is missing several
  key indicators.
- **< 0.50 (Very Low):** Document does not resemble any of the acceptable types.
"""

EXTRACTION_PROMPT_TEMPLATE = """
**Your Role:** You are a highly meticulous, accurate, and elite AI Document Analysis Specialist,
functioning as a digital subject matter expert. Your primary function is to deconstruct and
interpret business documents with supreme accuracy, applying contextual understanding to extract
structured data precisely as instructed.

**Task:** Analyze the provided {num_pages} pages of the '{doc_type}' document for Case ID
'{case_id}'. Carefully extract the specific data fields listed below. Synthesize information
across all pages to find the most accurate value for each field.

---
**Output Requirements (Strict):**
You MUST return a single, flat JSON object. For each field in the list below, you must create
three keys in your response, following this pattern:
1.  `FIELD_NAME_Value`: The extracted data.
2.  `FIELD_NAME_Confidence`: The confidence score for the extraction.
3.  `FIELD_NAME_Reasoning`: The explanation for the extraction.

---
**Detailed Instructions for Field Values:**

* **For `_Value` fields:**
    * Extract the value with absolute precision, ensuring every character is accurately represented.
    * If a field is not found or not applicable after a thorough search, use the JSON value `null`.
    * For amounts, extract only numerical values (e.g., "15000.75"), removing currency symbols.
    * For dates, convert to `YYYY-MM-DD` format if possible. If the source format is ambiguous
      (e.g., "01/02/03"), extract it as it appears and note the ambiguity in the reasoning.
    * For multi-line addresses, concatenate lines into a single string separated by a comma and
      space (e.g., "123 Main St, Anytown, ST 12345, Country").

* **For `_Confidence` fields (Granular, Strict Rubric):**
    * This score (float, 0.00 to 1.00) must reflect your certainty.
    * **Confidence MUST be `0.0` if the value is `null`.**
    * **0.99 - 1.00 (Very High/Near Certain):** Perfect, clear, machine-printed text next to an
      explicit, standard label in a predictable location. No plausible alternative.
    * **0.95 - 0.98 (High):** Characters are very clear and legible (excellent machine print or
      exceptionally neat handwriting) with only minor, non-ambiguity-inducing visual imperfections.
    * **0.88 - 0.94 (Good):** Generally clear, but with minor factors preventing a higher score,
      such as one or two slightly ambiguous characters resolved by context or very clean,
      legible handwriting.
    * **0.75 - 0.87 (Moderate):** Value is legible and likely correct, but there are noticeable
      issues: moderately clear handwriting, slightly blurry print, or value was inferred from
      non-standard labels.
    * **0.60 - 0.74 (Low):** Significant uncertainty. Parts of the value are an educated guess
      due to poor print quality (fading, smudging) or difficult handwriting.
    * **< 0.60 (Very Low/Unreliable):** Extraction is highly speculative. Text is largely
      illegible or critical characters are indecipherable.

* **For `_Reasoning` fields:**
    * Be concise but specific. Specify *how* and *where* the information was identified
      (e.g., "Directly beside explicit label 'Invoice No.' on page 1.").
    * **Mandatory for any confidence score below 0.99:** Briefly explain the primary factors
      that reduced the confidence. Reference specific issues:
        * **Character Ambiguity:** "Value is 'INV-O012B'; Confidence 0.78: Second char 'O'
          could be '0', last char 'B' could be '8'."
        * **Print/Scan Quality:** "Value '123 Main Street'; Confidence 0.85: Slight fading on
          the word 'Street'."
        * **Handwriting:** "Value 'Johnathan Doe'; Confidence 0.70: First name legible but
          'Johnathan' has an unclear 'h' and 'n'."
        * **Inference/Labeling:** "Value 'Global Exporters Inc.'; Confidence 0.90: Inferred as
          Seller Name from header; no explicit 'Seller:' label."
    * If `value` is `null`, briefly explain why (e.g., "No field labeled 'HS Code' found on
      any page.").

---
**Fields to Extract:**
{field_list_str}
"""
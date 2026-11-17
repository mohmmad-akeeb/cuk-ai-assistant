"""Input guardrails for Central University of Kashmir (CUK) Assistant.

Provides:
1. Fast local regex/keyword domain classifier ($0 cost, <1ms).
2. Groq Llama Guard 3 input safety rail (prompt injection & jailbreak detection).
3. Combined InputGuard orchestrator returning InputGuardResult.
"""

from __future__ import annotations

import logging
import os
import re
from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class FailureDiagnosticCode(StrEnum):
    """Standardized failure diagnostic attribution codes."""

    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    PARSING_DEFECT = "PARSING_DEFECT"
    QUESTION_PARSING_FAILED = "QUESTION_PARSING_FAILED"
    RETRIEVAL_EMPTY = "RETRIEVAL_EMPTY"
    RETRIEVAL_RECALL_MISS = "RETRIEVAL_RECALL_MISS"
    MISSED_TOP_RANKED = "MISSED_TOP_RANKED"
    CONTEXT_TRUNCATION = "CONTEXT_TRUNCATION"
    LLM_EXTRACTION_FAILURE = "LLM_EXTRACTION_FAILURE"
    LLM_HALLUCINATION = "LLM_HALLUCINATION"
    LLM_FORMAT_VIOLATION = "LLM_FORMAT_VIOLATION"
    OUTPUT_SAFETY_VIOLATION = "OUTPUT_SAFETY_VIOLATION"
    CORPUS_MISSING_CONTENT = "CORPUS_MISSING_CONTENT"


class InputGuardResult(BaseModel):
    """Result of evaluating user input against domain and safety guardrails."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_safe: bool
    is_in_domain: bool
    deflection_message: str | None = None
    diagnostic_code: str | FailureDiagnosticCode | None = None


DEFAULT_DOMAIN_DEFLECTION: str = (
    "I am the Central University of Kashmir (CUK) Assistant. I can only assist "
    "with university-related inquiries such as courses, syllabus, admissions, "
    "examinations, and official notifications."
)

DEFAULT_UNSAFE_DEFLECTION: str = (
    "This request violates university safety guidelines and cannot be processed."
)


class LocalDomainClassifier:
    """Fast deterministic domain router (<1ms, $0 cost).

    Classifies user queries as university in-domain or off-topic out-of-domain.
    """

    # Academic & University in-domain keywords and concepts
    _IN_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
        # University identity & locations
        re.compile(
            r"\b(cuk|central university of kashmir|cukashmir|kashmir university|"
            r"tulmulla|nunar|ganderbal|green campus|transit campus)\b",
            re.IGNORECASE,
        ),
        # Academic programs, degrees & curriculum
        re.compile(
            r"\b(b\.?tech|m\.?tech|mba|bba|ba\s*llb|b\.?a\.?\s*ll\.?b|llm|ll\.?m|b\.?ed|m\.?ed|"
            r"b\.?voc|m\.?voc|msc|m\.?sc|ma|m\.?a|phd|ph\.?d|m\.?phil|diploma|pg diploma|"
            r"undergraduate|postgraduate|ug|pg|doctoral|curriculum|syllabus|course|courses|"
            r"program|programs|programme|programmes|credits?|elective|semester|academic calendar|"
            r"subject|subjects|module|modules|unit|units|topic|topics|"
            r"book|books|textbook|textbooks|reference\s*books?|readings?|author|authors|"
            r"dbms|os|dsa|ai|ml|cn|se|oops|discrete math|data structures?|algorithms?|"
            r"database|operating systems?|networks?|compiler|automata|biotech|journalism)\b",
            re.IGNORECASE,
        ),
        # Admissions & Entrance
        re.compile(
            r"\b(admission|admissions|admit|apply|application|application form|cuet|cuet-ug|cuet-pg|"
            r"samarth|entrance|eligibility|counseling|counselling|cutoff|cut-off|merit list|"
            r"selection list|shortlist|intake|seat matrix|reservation|quota)\b",
            re.IGNORECASE,
        ),
        # Examinations & Results
        re.compile(
            r"\b(exam|exams|examination|examinations|date\s*sheet|datesheet|admit card|"
            r"hall ticket|exam center|exam centre|result|results|marks|grade|grades|cgpa|sgpa|"
            r"backlog|backlogs|re-evaluation|re-checking|rechecking|convocation|degree certificate|"
            r"transcript|transcripts|controller of examination|coe)\b",
            re.IGNORECASE,
        ),
        # Fees, Finance & Scholarships
        re.compile(
            r"\b(fee|fees|tuition|fee structure|refund|fee payment|scholarship|scholarships|"
            r"fellowship|fellowships|stipend|financial aid|nsp|merit-cum-means)\b",
            re.IGNORECASE,
        ),
        # Facilities, Campus Life & Services
        re.compile(
            r"\b(hostel|hostels|mess|accommodation|transport|bus|buses|bus route|bus timing|"
            r"library|books|reading room|wifi|internet|sports|gym|gymnasium|canteen|cafeteria|"
            r"health centre|dispensary|medical)\b",
            re.IGNORECASE,
        ),
        # Administration, Staff & Governance
        re.compile(
            r"\b(vice chancellor|vc|registrar|dean|head of department|hod|proctor|provost|"
            r"faculty|professor|assistant professor|associate professor|department|departments|"
            r"school of|directorate|administration|administrative|office|timing|timings|contact|"
            r"directory|email|phone number|extension)\b",
            re.IGNORECASE,
        ),
        # Official Notices, Circulars & Tenders
        re.compile(
            r"\b(notification|notifications|circular|circulars|notice|notices|order|orders|"
            r"tender|tenders|quotation|quotations|recruitment|job|jobs|vacancy|vacancies|"
            r"interview|walk-in|guest faculty|contractual|gazetted holiday|holidays)\b",
            re.IGNORECASE,
        ),
        # Common greeting & identity inquiries
        re.compile(
            r"\b(hi|hello|hey|good\s+(morning|afternoon|evening)|who are you|what can you do|"
            r"how can you help|help me)\b",
            re.IGNORECASE,
        ),
        # Academic Cohorts, Batches, Semesters, Degree codes & Disambiguation choices
        re.compile(
            r"^(20[12][0-9]|19[0-9]{2})$|"
            r"^\b(1st|2nd|3rd|4th|5th|6th|7th|8th|sem\s*[1-8]|semester\s*[1-8]|batch\s*20[12][0-9])\b$|"
            r"^\b(cse|it|mca|mba|bba|bvoc|b\.?tech|m\.?tech|b\.?sc|m\.?sc|ba\s*llb|llm|bed|m\.?ed|phd|m\.?phil|dbms|os|dsa|ai|ml)\b$|"
            r"^[1-9]$",
            re.IGNORECASE,
        ),
    )

    # Definite Out-of-Domain indicators
    _OUT_OF_DOMAIN_PATTERNS: tuple[re.Pattern[str], ...] = (
        # Coding & Software development prompts
        re.compile(
            r"\b(write|create|implement|debug|generate|fix|code)\b.*\b(python|javascript|typescript|"
            r"java|c\+\+|golang|rust|php|ruby|swift|html|css|sql|script|function|algorithm|"
            r"class|regex|quicksort|mergesort|binary search|fibonacci|leetcode)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(write\s+(a\s+)?(python|code|program|script|function|class)|"
            r"how to (code|program|debug|implement)|solve leetcode)",
            re.IGNORECASE,
        ),
        # Recipes & Cooking
        re.compile(
            r"\b(recipe|how to (cook|bake|make)|ingredients for)\b.*\b(biryani|pizza|cake|bread|"
            r"soup|tea|curry|pasta|coffee|cookies|dish|chicken|mutton|paneer)\b",
            re.IGNORECASE,
        ),
        # Creative writing & Entertainment
        re.compile(
            r"\b(write\s+(a\s+)?(poem|story|song|essay|novel|joke|rap|fairy tale)|"
            r"tell me a joke|movie review)\b",
            re.IGNORECASE,
        ),
        # World general trivia & Non-academic general queries
        re.compile(
            r"\b(capital of (france|germany|italy|japan|spain|usa|canada|brazil|russia|australia)|"
            r"president of (usa|france|america|russia)|tallest mountain|speed of light|"
            r"who won the (world cup|fifa|ipl|super bowl|olympics)|distance to (moon|mars|sun))\b",
            re.IGNORECASE,
        ),
        # Pure math equation solving unrelated to syllabus
        re.compile(
            r"^(solve\s+([0-9x\+\-\*\/\^\(\)\s=]+)|integrate\s+|derivative of\s+)",
            re.IGNORECASE,
        ),
    )

    def classify(self, query: str) -> tuple[bool, str | None]:
        """Classify query domain.

        Returns:
            tuple[bool, str | None]: (is_in_domain, deflection_message)
        """
        cleaned = query.strip()
        if not cleaned:
            return False, DEFAULT_DOMAIN_DEFLECTION

        # Check explicit out-of-domain patterns first
        for out_pat in self._OUT_OF_DOMAIN_PATTERNS:
            if out_pat.search(cleaned):
                return False, DEFAULT_DOMAIN_DEFLECTION

        # Check in-domain patterns
        for in_pat in self._IN_DOMAIN_PATTERNS:
            if in_pat.search(cleaned):
                return True, None

        # If query has no university terms and is a generic query, deflect
        # Queries of length <= 3 without matching in-domain are deflected
        if len(cleaned) <= 3:
            return False, DEFAULT_DOMAIN_DEFLECTION

        # Fallback: if query mentions general academic inquiry words, allow
        general_academic = re.search(
            r"\b(student|students|teacher|teachers|class|classes|lecture|lectures|"
            r"semester|exam|study|campus|college|university|result|syllabus|fee|"
            r"book|books|textbook|textbooks|subject|subjects|credit|credits|paper|papers)\b",
            cleaned,
            re.IGNORECASE,
        )
        if general_academic:
            return True, None

        return False, DEFAULT_DOMAIN_DEFLECTION


class GroqLlamaGuardRail:
    """Evaluates query safety using Groq's Llama Guard 3 8B model with local fallback."""

    DEFAULT_GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"
    DEFAULT_MODEL: str = "llama-guard-3-8b"

    # Local fallback heuristics for prompt injection & jailbreak detection
    _INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|above)?\s*"
            r"(instructions|directions|prompts|rules|system instructions)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(you are now|pretend you are|act as)\s+(dan|an unrestricted|a developer|"
            r"jailbroken|evil assistant|chaos gpt)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(reveal|output|display|show|print|leak)\b.*?\b(system prompt|"
            r"internal instructions|hidden prompt|initial prompt)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(bypass|disable|turn off|circumvent)\s+(the\s+)?(safety\s+)?"
            r"(guardrails?|filters?|rules?|policy)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(jailbreak|jailbroken)\b",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_GROQ_API_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 3.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    def _local_scan(self, text: str) -> tuple[bool, str | None]:
        """Local heuristic scan for prompt injection and malicious keywords."""
        for pattern in self._INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return False, f"local_heuristic_injection:{match.group(0)}"
        return True, None

    def scan_input(self, text: str) -> tuple[bool, str | None]:
        """Synchronously scan input text for safety violations."""
        # Always run fast local heuristic first
        safe_local, reason_local = self._local_scan(text)
        if not safe_local:
            return False, reason_local

        if not self.api_key:
            logger.debug("GROQ_API_KEY not set; using local heuristic safety check only.")
            return True, None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "temperature": 0.0,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.base_url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    )
                    if content.lower().startswith("unsafe"):
                        return False, content
                    return True, None
                else:
                    logger.warning(
                        "Groq API returned HTTP %s: %s; falling back to local heuristic.",
                        response.status_code,
                        response.text,
                    )
                    return True, None
        except Exception as e:
            logger.warning("Groq API call failed (%s); falling back to local heuristic.", e)
            return True, None

    async def scan_input_async(self, text: str) -> tuple[bool, str | None]:
        """Asynchronously scan input text for safety violations."""
        safe_local, reason_local = self._local_scan(text)
        if not safe_local:
            return False, reason_local

        if not self.api_key:
            return True, None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "temperature": 0.0,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    )
                    if content.lower().startswith("unsafe"):
                        return False, content
                    return True, None
                else:
                    logger.warning("Groq API returned HTTP %s", response.status_code)
                    return True, None
        except Exception as e:
            logger.warning("Groq async API call failed (%s)", e)
            return True, None


class InputGuard:
    """Orchestrates domain classification and safety rail validation."""

    def __init__(
        self,
        domain_classifier: LocalDomainClassifier | None = None,
        safety_rail: GroqLlamaGuardRail | None = None,
    ) -> None:
        self.domain_classifier = domain_classifier or LocalDomainClassifier()
        self.safety_rail = safety_rail or GroqLlamaGuardRail()

    def validate_query(self, query: str) -> InputGuardResult:
        """Alias for validate(), conforming to RAG pipeline orchestrator contract."""
        return self.validate(query)

    def validate(self, raw_query: str) -> InputGuardResult:
        """Synchronously validate user query against domain and safety rules."""
        is_in_domain, domain_deflection = self.domain_classifier.classify(raw_query)
        if not is_in_domain:
            return InputGuardResult(
                is_safe=True,
                is_in_domain=False,
                deflection_message=domain_deflection or DEFAULT_DOMAIN_DEFLECTION,
                diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
            )

        is_safe, safety_reason = self.safety_rail.scan_input(raw_query)
        if not is_safe:
            return InputGuardResult(
                is_safe=False,
                is_in_domain=True,
                deflection_message=DEFAULT_UNSAFE_DEFLECTION,
                diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
            )

        return InputGuardResult(
            is_safe=True,
            is_in_domain=True,
            deflection_message=None,
            diagnostic_code=None,
        )

    async def validate_async(self, raw_query: str) -> InputGuardResult:
        """Asynchronously validate user query against domain and safety rules."""
        is_in_domain, domain_deflection = self.domain_classifier.classify(raw_query)
        if not is_in_domain:
            return InputGuardResult(
                is_safe=True,
                is_in_domain=False,
                deflection_message=domain_deflection or DEFAULT_DOMAIN_DEFLECTION,
                diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
            )

        is_safe, safety_reason = await self.safety_rail.scan_input_async(raw_query)
        if not is_safe:
            return InputGuardResult(
                is_safe=False,
                is_in_domain=True,
                deflection_message=DEFAULT_UNSAFE_DEFLECTION,
                diagnostic_code=FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
            )

        return InputGuardResult(
            is_safe=True,
            is_in_domain=True,
            deflection_message=None,
            diagnostic_code=None,
        )

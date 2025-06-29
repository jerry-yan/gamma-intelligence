# ── SCHEMAS ─────────────────────────────────────────
INITIATION_REPORT_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {"type": "string"},
                "title": {"type": "string"},
                "source": {"type": "string"},
                "authors": {
                    "type": "array",
                    "description": "Author or authors in the reported. Can be omitted if not found.",
                    "items": {"type": "string"},
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"]
                },
                "summary": {"type": "string"},
                "positive_dynamics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "negative_dynamics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "upside_valuation": {"type": "string"},
                "downside_valuation": {"type": "string"},
                "conclusion": {"type": "string"},
            },
            "required": ["stock_ticker", "title", "source", "authors", "sentiment", "summary", "positive_dynamics", "negative_dynamics", "upside_valuation", "downside_valuation", "conclusion"],
            "additionalProperties": False,
        },
    },
}

COMPANY_UPDATE_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {
                    "type": "string",
                    "description": "Explicit stock ticker symbol from the report (e.g., GOOGL)."
                },
                "title": {
                    "type": "string",
                    "description": "Exact title of the provided report."
                },
                "source": {
                    "type": "string",
                    "description": "The name of the firm or entity that published the report."
                },
                "authors": {
                        "type": "array",
                        "description": "Author or authors in the reported. Can be omitted if not found.",
                        "items": {"type": "string"},
                    },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"],
                    "description": "Overall sentiment or opinion of the author towards the stock."
                },
                "price_target": {
                    "type": ["number", "null"],
                    "description": "Specific numerical price target from the report or null if none provided."
                },
                "stock_rating": {
                    "type": ["string", "null"],
                    "description": "The stock rating given by the broker in the report or null if none provided.",
                    "enum": ["Buy", "Hold", "Sell"]
                },
                "executive_summary": {
                    "type": "string",
                    "description": "Concise executive summary including recent events, key developments, relevant analysis, updated valuation insights, and important points from the report (approximately 100-120 words)."
                },
                "bull_points": {
                    "type": "array",
                    "description": "Explicit, clear bullet points on bullish arguments directly from the report.",
                    "items": {"type": "string"}
                },
                "bear_points": {
                    "type": "array",
                    "description": "Explicit, clear bullet points on bearish arguments directly from the report.",
                    "items": {"type": "string"}
                },
                "valuation_analysis": {
                    "type": ["string", "null"],
                    "description": "Brief summary (approximately 40-60 words) of valuation methods, assumptions, or key insights from the report. Null if no valuation analysis provided."
                },
                "extra_details": {
                    "type": "string",
                    "description": "Detailed elaboration significantly expanding upon executive summary, bullish and bearish arguments, and valuation analysis. Provide specific evidence, data points, quotations from the analyst or report, clearly explained valuation assumptions or methods, and deeper analytical insights explicitly from the report. Must strictly contain between 310 and 350 words and avoid verbatim repetition of content from the primary summary."
                },
            },
            "required": [
                "stock_ticker", "title", "source", "authors", "sentiment", "price_target", "stock_rating",
                "executive_summary", "bull_points", "bear_points", "valuation_analysis",
                "extra_details"
            ],
            "additionalProperties": False
        }
    }
}

QUARTER_PREVIEW_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {
                    "type": "string",
                    "description": "The stock ticker explicitly identified in the report (e.g., MSFT)."
                },
                "title": {
                    "type": "string",
                    "description": "The exact title of the provided report."
                },
                "source": {
                    "type": "string",
                    "description": "The name of the firm or analyst that published the report."
                },
                "authors": {
                        "type": "array",
                        "description": "Author or authors in the reported. Can be omitted if not found.",
                        "items": {"type": "string"},
                    },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"],
                    "description": "The overall sentiment or outlook of the author toward the stock."
                },
                "price_target": {
                    "type": ["number", "null"],
                    "description": "Specific numerical price target from the report, or null if not provided."
                },
                "stock_rating": {
                    "type": ["string", "null"],
                    "description": "The stock rating given by the broker in the report or null if none provided.",
                    "enum": ["Buy", "Hold", "Sell"]
                },
                "summary": {
                    "type": "string",
                    "description": "Concise general summary of key points from the report, including important events, developments, and main findings (approximately 80-100 words)."
                },
                "expectations": {
                    "type": "string",
                    "description": "Detailed summary of expectations heading into earnings, clearly including qualitative factors (such as strategic developments, management guidance) and quantitative factors (such as expected EPS, revenue figures). Approximately 60-80 words."
                },
                "risk_points": {
                    "type": "array",
                    "description": "Clearly listed bullet points detailing specific risks explicitly mentioned in the report.",
                    "items": {"type": "string"}
                },
                "opportunity_points": {
                    "type": "array",
                    "description": "Clearly listed bullet points detailing specific opportunities explicitly mentioned in the report.",
                    "items": {"type": "string"}
                },
                "valuation_analysis": {
                    "type": ["string", "null"],
                    "description": "Brief but clear summary of any valuation analysis methods, assumptions, or insights from the report (around 40-60 words). Null if not provided."
                },
                "extra_details": {
                    "type": "string",
                    "description": "Detailed elaboration significantly expanding upon summary, expectations, risks, opportunities, and valuation analysis. Provide specific evidence, examples, numerical data, analyst quotations, valuation methodology details, and deeper analytical insights explicitly sourced from the report. Must strictly contain between 290 and 310 words without repeating verbatim the primary summary."
                },
            },
            "required": [
                "stock_ticker", "title", "source", "authors", "sentiment", "price_target", "stock_rating",
                "summary", "expectations", "risk_points", "opportunity_points",
                "valuation_analysis", "extra_details"
            ],
            "additionalProperties": False
        }
    }
}

QUARTER_REVIEW_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {
                    "type": "string",
                    "description": "The stock ticker explicitly mentioned in the report (e.g., AAPL)."
                },
                "title": {
                    "type": "string",
                    "description": "The exact title of the report provided."
                },
                "source": {
                    "type": "string",
                    "description": "The name of the firm or entity that published the report."
                },
                "authors": {
                            "type": "array",
                            "description": "Author or authors in the reported. Can be omitted if not found.",
                            "items": {"type": "string"},
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"],
                    "description": "The overall sentiment or stance toward the stock from the author’s perspective."
                },
                "price_target": {
                    "type": "number",
                    "description": "The specific numerical price target provided in the report (e.g., 145.00)."
                },
                "stock_rating": {
                    "type": ["string", "null"],
                    "description": "The stock rating given by the broker in the report or null if none provided.",
                    "enum": ["Buy", "Hold", "Sell"]
                },
                "recap": {
                    "type": "string",
                    "description": "A concise, clearly written recap of the key points of the report, including recent developments, key financial or market updates, and relevant analysis. Approximately 100-150 words."
                },
                "bull_points": {
                    "type": "array",
                    "description": "List distinct bullish points from the report, clearly summarized.",
                    "items": {"type": "string"}
                },
                "bear_points": {
                    "type": "array",
                    "description": "List distinct bearish points from the report, clearly summarized.",
                    "items": {"type": "string"}
                },
                "valuation_analysis": {
                    "type": "string",
                    "description": "Clear summary of the valuation analysis methods, assumptions, key metrics, or insights provided explicitly in the report."
                },
                "extra_details": {
                    "type": "string",
                    "description": "Additional detailed elaboration expanding significantly on points mentioned previously (such as recap, bull and bear points, valuation). Provide specific evidence, quotes, data, numbers, or analytical insights from the report. Must be at least 290 words and no more than 310 words."
                },
            },
            "required": [
                "stock_ticker",
                "title",
                "source",
                "authors",
                "sentiment",
                "price_target",
                "stock_rating",
                "recap",
                "bull_points",
                "bear_points",
                "valuation_analysis",
                "extra_details"
            ],
            "additionalProperties": False
        }
    }
}


INDUSTRY_NOTE_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "source": {
                    "type": "string",
                    "description": "The title of the report"
                },
                "authors": {
                            "type": "array",
                            "description": "Author or authors in the reported. Can be omitted if not found.",
                            "items": {"type": "string"},
                        },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"]
                },
                "executive_summary": {"type": "string"},
                "key_dynamics": {
                    "type": "array",
                    "description": "Key industry dynamics, challenges, risk, opportunities and analysis",
                    "items": {"type": "string"},
                },
                "valuation_analysis": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "stock_recaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "stock_ticker": {
                                "type": "string",
                                "description": "The ticker symbol given in the report. If N/A, you can instead give the industry name."
                            },
                            "stock_rating": {
                                "type": ["string", "null"],
                                "enum": ["Buy", "Hold", "Sell", "None"]
                            },
                            "stock_outlook": {
                                "type": "string",
                                "description": "A concise, clearly written recap of the outlook for the stock such as headwinds and tailwinds."
                            },
                            "stock_valuation": {
                                "type": ["string", "null"],
                                "description": "Clear summary of the valuation analysis methods, assumptions, key metrics, or insights provided explicitly in the report. Only mention the price target here if explicitly mentioned in the report."
                            },
                        },
                        "required": ["stock_ticker", "stock_rating", "stock_outlook", "stock_valuation"],
                        "additionalProperties": False
                    },
                },
            },
            "required": ["title", "source", "authors", "sentiment", "executive_summary", "key_dynamics", "valuation_analysis", "stock_recaps"],
            "additionalProperties": False,
        },
    },
}

MACRO_REPORT_SCHEMA = {
            "format": {
                "type": "json_schema",
                "name": "report_summary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "source": {"type": "string"},
                        "authors": {
                            "type": "array",
                            "description": "Author or authors in the reported. Can be omitted if not found.",
                            "items": {"type": "string"},
                        },
                        "sentiment": {
                            "type": "string",
                            "enum": ["Positive", "Neutral", "Negative"]
                        },"executive_summary": {"type": "string"},
                        "key_themes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "valuation_analysis": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "strategic_recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "authors", "source", "sentiment", "executive_summary", "key_themes", "valuation_analysis", "strategic_recommendations"],
                    "additionalProperties": False,
                },
            },
        }

SCHEMAS = {
    "Initiation Report": INITIATION_REPORT_SCHEMA,
    "Company Update": COMPANY_UPDATE_SCHEMA,
    "Quarter Preview": QUARTER_PREVIEW_SCHEMA,
    "Quarter Review": QUARTER_REVIEW_SCHEMA,
    "Industry Note": INDUSTRY_NOTE_SCHEMA,
    "Macro/Strategy Report": MACRO_REPORT_SCHEMA,
}

# ── ADVANCED SCHEMAS ─────────────────────────────────────────
ADVANCED_INITIATION_REPORT_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {"type": "string"},
                "title": {"type": "string"},
                "source": {"type": "string"},
                "authors": {
                    "type": "array",
                    "description": "Author or authors in the reported. Can be omitted if not found.",
                    "items": {"type": "string"},
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"]
                },
                "summary": {"type": "string"},
                "positive_dynamics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "negative_dynamics": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "upside_valuation": {"type": "string"},
                "downside_valuation": {"type": "string"},
                "conclusion": {"type": "string"},
            },
            "required": ["stock_ticker", "title", "source", "authors", "sentiment", "summary", "positive_dynamics", "negative_dynamics", "upside_valuation", "downside_valuation", "conclusion"],
            "additionalProperties": False,
        },
    },
}

ADVANCED_COMPANY_UPDATE_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {
                    "type": "string",
                    "description": "Explicit stock ticker symbol from the report (e.g., GOOGL)."
                },
                "title": {
                    "type": "string",
                    "description": "Exact title of the provided report."
                },
                "source": {
                    "type": "string",
                    "description": "The name of the firm or entity that published the report."
                },
                "authors": {
                        "type": "array",
                        "description": "Author or authors in the reported. Can be omitted if not found.",
                        "items": {"type": "string"},
                    },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"],
                    "description": "Overall sentiment or opinion of the author towards the stock."
                },
                "price_target": {
                    "type": ["number", "null"],
                    "description": "Specific numerical price target from the report or null if none provided."
                },
                "stock_rating": {
                    "type": ["string", "null"],
                    "description": "The stock rating given by the broker in the report or null if none provided.",
                    "enum": ["Buy", "Hold", "Sell"]
                },
                "executive_summary": {
                    "type": "string",
                    "description": "Concise executive summary including recent events, key developments, relevant analysis, updated valuation insights, and important points from the report (approximately 190-300 words)."
                },
                "bull_points": {
                    "type": "array",
                    "description": "Explicit, clear bullet points on bullish arguments directly from the report.",
                    "items": {"type": "string"}
                },
                "bear_points": {
                    "type": "array",
                    "description": "Explicit, clear bullet points on bearish arguments directly from the report.",
                    "items": {"type": "string"}
                },
                "valuation_analysis": {
                    "type": ["string", "null"],
                    "description": "Brief summary (approximately 80-130 words) of valuation methods, assumptions, or key insights from the report. Null if no valuation analysis provided."
                },
                "extra_details": {
                    "type": "string",
                    "description": "Detailed elaboration significantly expanding upon executive summary, bullish and bearish arguments, and valuation analysis. Provide specific evidence, data points, quotations from the analyst or report, clearly explained valuation assumptions or methods, and deeper analytical insights explicitly from the report. Must strictly contain between 600 and 700 words and avoid verbatim repetition of content from the primary summary."
                },
            },
            "required": [
                "stock_ticker", "title", "source", "authors", "sentiment", "price_target", "stock_rating",
                "executive_summary", "bull_points", "bear_points", "valuation_analysis",
                "extra_details"
            ],
            "additionalProperties": False
        }
    }
}

ADVANCED_QUARTER_PREVIEW_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {
                    "type": "string",
                    "description": "The stock ticker explicitly identified in the report (e.g., MSFT)."
                },
                "title": {
                    "type": "string",
                    "description": "The exact title of the provided report."
                },
                "source": {
                    "type": "string",
                    "description": "The name of the firm or analyst that published the report."
                },
                "authors": {
                        "type": "array",
                        "description": "Author or authors in the reported. Can be omitted if not found.",
                        "items": {"type": "string"},
                    },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"],
                    "description": "The overall sentiment or outlook of the author toward the stock."
                },
                "price_target": {
                    "type": ["number", "null"],
                    "description": "Specific numerical price target from the report, or null if not provided."
                },
                "stock_rating": {
                    "type": ["string", "null"],
                    "description": "The stock rating given by the broker in the report or null if none provided.",
                    "enum": ["Buy", "Hold", "Sell"]
                },
                "summary": {
                    "type": "string",
                    "description": "Concise general summary of key points from the report, including important events, developments, and main findings (approximately 160-200 words)."
                },
                "expectations": {
                    "type": "string",
                    "description": "Detailed summary of expectations heading into earnings, clearly including qualitative factors (such as strategic developments, management guidance) and quantitative factors (such as expected EPS, revenue figures). Approximately 100-180 words."
                },
                "risk_points": {
                    "type": "array",
                    "description": "Clearly listed bullet points detailing specific risks explicitly mentioned in the report.",
                    "items": {"type": "string"}
                },
                "opportunity_points": {
                    "type": "array",
                    "description": "Clearly listed bullet points detailing specific opportunities explicitly mentioned in the report.",
                    "items": {"type": "string"}
                },
                "valuation_analysis": {
                    "type": ["string", "null"],
                    "description": "Brief but clear summary of any valuation analysis methods, assumptions, or insights from the report (around 80-130 words). Null if not provided."
                },
                "extra_details": {
                    "type": "string",
                    "description": "Detailed elaboration significantly expanding upon summary, expectations, risks, opportunities, and valuation analysis. Provide specific evidence, examples, numerical data, analyst quotations, valuation methodology details, and deeper analytical insights explicitly sourced from the report. Must strictly contain between 500 and 700 words without repeating verbatim the primary summary."
                },
            },
            "required": [
                "stock_ticker", "title", "source", "authors", "sentiment", "price_target", "stock_rating",
                "summary", "expectations", "risk_points", "opportunity_points",
                "valuation_analysis", "extra_details"
            ],
            "additionalProperties": False
        }
    }
}

ADVANCED_QUARTER_REVIEW_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stock_ticker": {
                    "type": "string",
                    "description": "The stock ticker explicitly mentioned in the report (e.g., AAPL)."
                },
                "title": {
                    "type": "string",
                    "description": "The exact title of the report provided."
                },
                "source": {
                    "type": "string",
                    "description": "The name of the firm or entity that published the report."
                },
                "authors": {
                            "type": "array",
                            "description": "Author or authors in the reported. Can be omitted if not found.",
                            "items": {"type": "string"},
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"],
                    "description": "The overall sentiment or stance toward the stock from the author’s perspective."
                },
                "price_target": {
                    "type": "number",
                    "description": "The specific numerical price target provided in the report (e.g., 145.00)."
                },
                "stock_rating": {
                    "type": ["string", "null"],
                    "description": "The stock rating given by the broker in the report or null if none provided.",
                    "enum": ["Buy", "Hold", "Sell"]
                },
                "recap": {
                    "type": "string",
                    "description": "A concise, clearly written recap of the key points of the report, including recent developments, key financial or market updates, and relevant analysis. Approximately 190-300 words."
                },
                "bull_points": {
                    "type": "array",
                    "description": "List distinct bullish points from the report, clearly summarized.",
                    "items": {"type": "string"}
                },
                "bear_points": {
                    "type": "array",
                    "description": "List distinct bearish points from the report, clearly summarized.",
                    "items": {"type": "string"}
                },
                "valuation_analysis": {
                    "type": "string",
                    "description": "Clear summary of the valuation analysis methods, assumptions, key metrics, or insights provided explicitly in the report."
                },
                "extra_details": {
                    "type": "string",
                    "description": "Additional detailed elaboration expanding significantly on points mentioned previously (such as recap, bull and bear points, valuation). Provide specific evidence, quotes, data, numbers, or analytical insights from the report. Must be at least 500 words and no more than 700 words."
                },
            },
            "required": [
                "stock_ticker",
                "title",
                "source",
                "authors",
                "sentiment",
                "price_target",
                "stock_rating",
                "recap",
                "bull_points",
                "bear_points",
                "valuation_analysis",
                "extra_details"
            ],
            "additionalProperties": False
        }
    }
}


ADVANCED_INDUSTRY_NOTE_SCHEMA = {
    "format": {
        "type": "json_schema",
        "name": "report_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "source": {
                    "type": "string",
                    "description": "The title of the report"
                },
                "authors": {
                            "type": "array",
                            "description": "Author or authors in the reported. Can be omitted if not found.",
                            "items": {"type": "string"},
                        },
                "sentiment": {
                    "type": "string",
                    "enum": ["Positive", "Neutral", "Negative"]
                },
                "executive_summary": {"type": "string"},
                "key_dynamics": {
                    "type": "array",
                    "description": "Key industry dynamics, challenges, risk, opportunities and analysis",
                    "items": {"type": "string"},
                },
                "valuation_analysis": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "stock_recaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "stock_ticker": {
                                "type": "string",
                                "description": "The ticker symbol given in the report. If N/A, you can instead give the industry name."
                            },
                            "stock_rating": {
                                "type": ["string", "null"],
                                "enum": ["Buy", "Hold", "Sell", "None"]
                            },
                            "stock_outlook": {
                                "type": "string",
                                "description": "A concise, clearly written recap of the outlook for the stock such as headwinds and tailwinds."
                            },
                            "stock_valuation": {
                                "type": ["string", "null"],
                                "description": "Clear summary of the valuation analysis methods, assumptions, key metrics, or insights provided explicitly in the report. Only mention the price target here if explicitly mentioned in the report."
                            },
                        },
                        "required": ["stock_ticker", "stock_rating", "stock_outlook", "stock_valuation"],
                        "additionalProperties": False
                    },
                },
            },
            "required": ["title", "source", "authors", "sentiment", "executive_summary", "key_dynamics", "valuation_analysis", "stock_recaps"],
            "additionalProperties": False,
        },
    },
}

ADVANCED_MACRO_REPORT_SCHEMA = {
            "format": {
                "type": "json_schema",
                "name": "report_summary",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "source": {"type": "string"},
                        "authors": {
                            "type": "array",
                            "description": "Author or authors in the reported. Can be omitted if not found.",
                            "items": {"type": "string"},
                        },
                        "sentiment": {
                            "type": "string",
                            "enum": ["Positive", "Neutral", "Negative"]
                        },"executive_summary": {"type": "string"},
                        "key_themes": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "valuation_analysis": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "strategic_recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "authors", "source", "sentiment", "executive_summary", "key_themes", "valuation_analysis", "strategic_recommendations"],
                    "additionalProperties": False,
                },
            },
        }

ADVANCED_SCHEMAS = {
    "Initiation Report": ADVANCED_INITIATION_REPORT_SCHEMA,
    "Company Update": ADVANCED_COMPANY_UPDATE_SCHEMA,
    "Quarter Preview": ADVANCED_QUARTER_PREVIEW_SCHEMA,
    "Quarter Review": ADVANCED_QUARTER_REVIEW_SCHEMA,
    "Industry Note": ADVANCED_INDUSTRY_NOTE_SCHEMA,
    "Macro/Strategy Report": ADVANCED_MACRO_REPORT_SCHEMA,
}
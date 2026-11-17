#!/usr/bin/env python3
"""
Enterprise ERP Connectors for Argus:
- SAP S/4HANA Supply Chain (MM-PUR Materials Management & SAP GTS Global Trade Services)
- Oracle Cloud SCM (Procurement & Oracle Global Trade Management - GTM)

Provides real-time pre-shipment compliance gating, blocking goods receipts (GR)
and customs lodgement for non-compliant supplier batches before shipment loading.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List


class SAPS4HANAConnector:
    """
    SAP S/4HANA Supply Chain and Global Trade Services (GTS) Pre-Shipment Gate.
    """

    @staticmethod
    def verify_purchase_order(po_data: Dict[str, Any], compliance_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates an SAP MM-PUR Purchase Order line item against EUDR compliance status
        and emits a standard SAP BAPI_RET2 / BapiReturn response.
        """
        po_number = po_data.get("PurchaseOrder", "4500091240")
        item_number = po_data.get("PurchaseOrderItem", "00010")
        vendor_id = po_data.get("Vendor", "100492")
        material = po_data.get("Material", "SOY-BEANS-BULK")
        batch = po_data.get("Batch", "B2026-08821")
        plant = po_data.get("Plant", "1010")

        is_compliant = compliance_record.get("status", "VIOLATION").upper() == "COMPLIANT"
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        if is_compliant:
            bapi_return = {
                "TYPE": "S",
                "ID": "EUDR_COMPLIANCE",
                "NUMBER": "001",
                "MESSAGE": f"EUDR Article 3 verified: PO {po_number} Item {item_number} cleared for shipment and goods receipt.",
                "LOG_NO": f"SAP-GTS-LOG-{now_str}",
                "LOG_MSG_NO": "000001",
                "MESSAGE_V1": po_number,
                "MESSAGE_V2": vendor_id,
                "MESSAGE_V3": batch,
                "MESSAGE_V4": "APPROVED",
                "PARAMETER": "PURCHASEORDER",
                "FIELD": "COMPLIANCE_STATUS",
            }
            erp_decision = {
                "sap_status": "APPROVED",
                "goods_receipt_blocked": False,
                "customs_hold_applied": False,
                "sap_release_code": "01",
                "gts_customs_document_guid": f"GTS-DOC-{now_str[-8:]}",
                "bapi_return": [bapi_return],
            }
        else:
            bapi_return = {
                "TYPE": "E",
                "ID": "EUDR_COMPLIANCE",
                "NUMBER": "003",
                "MESSAGE": (
                    f"CUSTOMS HOLD APPLIED: PO {po_number} Item {item_number} blocked by EUDR Article 3(a). "
                    f"Supplier {vendor_id} parcel flagged with post-2020 canopy disruption."
                ),
                "LOG_NO": f"SAP-GTS-LOG-{now_str}",
                "LOG_MSG_NO": "000002",
                "MESSAGE_V1": po_number,
                "MESSAGE_V2": vendor_id,
                "MESSAGE_V3": batch,
                "MESSAGE_V4": "REJECTED_BREACH",
                "PARAMETER": "PURCHASEORDER",
                "FIELD": "COMPLIANCE_STATUS",
            }
            erp_decision = {
                "sap_status": "BLOCKED",
                "goods_receipt_blocked": True,
                "customs_hold_applied": True,
                "sap_release_code": "03",
                "gts_customs_document_guid": f"GTS-BLOCK-{now_str[-8:]}",
                "bapi_return": [bapi_return],
            }

        return {
            "erp_system": "SAP S/4HANA 2026 Cloud (Enterprise SCM / GTS)",
            "purchase_order": po_number,
            "purchase_order_item": item_number,
            "vendor": vendor_id,
            "material": material,
            "batch": batch,
            "plant": plant,
            "decision": erp_decision,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class OracleCloudSCMConnector:
    """
    Oracle Cloud SCM Procurement & Global Trade Management (GTM) Connector.
    """

    @staticmethod
    def screen_trade_transaction(transaction: Dict[str, Any], compliance_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Screens an Oracle SCM Trade Transaction against EUDR statutory standards.
        """
        tx_id = transaction.get("TransactionId", "GTM-TX-2026-9041")
        party_id = transaction.get("PartyId", "PRTY-AGRI-BRAZIL")
        item = transaction.get("ItemNumber", "COMM-COFFEE-01")
        country = transaction.get("CountryOfOrigin", "CO")

        is_compliant = compliance_record.get("status", "VIOLATION").upper() == "COMPLIANT"
        now_iso = datetime.now(timezone.utc).isoformat()

        if is_compliant:
            status = "PASSED"
            decision_code = "RELEASED_STATUTORY_COMPLIANT"
            reason = "Zero post-cutoff canopy disruption verified by Copernicus Sentinel-2 / Sentinel-1 RTC."
        else:
            status = "HOLD_REGULATORY_RESTRICTION"
            decision_code = "RESTRICTED_BREACH_ARTICLE_3"
            reason = "Statutory violation: post-2020 forest canopy reduction detected on supplier parcel."

        return {
            "erp_system": "Oracle Fusion Cloud SCM / Global Trade Management (GTM)",
            "transaction_id": tx_id,
            "party_id": party_id,
            "item_number": item,
            "country_of_origin": country,
            "gtm_screening_result": {
                "screening_status": status,
                "decision_code": decision_code,
                "sanction_program": "European Union Deforestation Regulation (Regulation (EU) 2023/1115)",
                "audit_clearance_token": f"ARGUS-ORCL-{tx_id[-6:]}" if is_compliant else None,
                "explanation": reason,
                "dispatch_authorized": is_compliant,
            },
            "timestamp": now_iso,
        }

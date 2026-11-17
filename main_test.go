package main

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTracesExportXML(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/traces/export?format=xml&plot_id=PLOT-BR-8821&commodity=Soy&status=VIOLATION", nil)
	w := httptest.NewRecorder()

	handleTracesExport(w, req)

	res := w.Result()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", res.StatusCode)
	}

	body := w.Body.String()
	if !strings.Contains(body, "<DueDiligenceStatement") {
		t.Errorf("expected XML DueDiligenceStatement root element, got: %s", body)
	}
	if !strings.Contains(body, "Regulation (EU) 2023/1115") {
		t.Errorf("expected EUDR regulation reference in XML")
	}
	if !strings.Contains(body, "SHA-256") {
		t.Errorf("expected SHA-256 seal in XML")
	}
	if !strings.Contains(body, "CUSTOMS_HOLD_ARTICLE_3") {
		t.Errorf("expected CUSTOMS_HOLD_ARTICLE_3 for violation")
	}
}

func TestTracesExportJSON(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/traces/export?format=json&plot_id=PLOT-CO-1049&commodity=Coffee&status=COMPLIANT", nil)
	w := httptest.NewRecorder()

	handleTracesExport(w, req)

	res := w.Result()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d", res.StatusCode)
	}

	var data map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &data); err != nil {
		t.Fatalf("failed to parse JSON response: %v", err)
	}

	if data["statement_reference"] != "DDS-2026-EUDR-1049" {
		t.Errorf("expected reference DDS-2026-EUDR-1049, got %v", data["statement_reference"])
	}

	seal, ok := data["cryptographic_seal"].(map[string]interface{})
	if !ok || seal["hash_seal"] == "" {
		t.Errorf("missing cryptographic seal in JSON output")
	}
}

func TestTracesVerify(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/api/traces/verify?hash=8f4c9b1e2a784d0b9854d194c718ea912389ab426210f562cd8371901a1c94b2", nil)
	w := httptest.NewRecorder()

	handleTracesVerify(w, req)

	var data map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &data); err != nil {
		t.Fatalf("failed to parse JSON response: %v", err)
	}

	if data["verified"] != true {
		t.Errorf("expected verified == true")
	}
	if data["certificate_status"] != "VALID_IMMUTABLE_RECORD" {
		t.Errorf("expected VALID_IMMUTABLE_RECORD")
	}
}

func TestParcelsValidate(t *testing.T) {
	geojsonPayload := `{
		"type": "FeatureCollection",
		"features": [
			{
				"type": "Feature",
				"properties": {"id": "TEST-FARM-01", "commodity": "Coffee", "status": "COMPLIANT"},
				"geometry": {
					"type": "Polygon",
					"coordinates": [[[-75.62, 2.53], [-75.61, 2.53], [-75.61, 2.54], [-75.62, 2.54], [-75.62, 2.53]]]
				}
			},
			{
				"type": "Feature",
				"properties": {"id": "TEST-FARM-02-VIOL", "commodity": "Soy"},
				"geometry": {
					"type": "Polygon",
					"coordinates": [[[-55.62, -10.85], [-55.61, -10.85], [-55.61, -10.84], [-55.62, -10.84], [-55.62, -10.85]]]
				}
			}
		]
	}`

	req := httptest.NewRequest(http.MethodPost, "/api/parcels/validate", bytes.NewBufferString(geojsonPayload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	handleParcelsValidate(w, req)

	res := w.Result()
	if res.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK, got %d: %s", res.StatusCode, w.Body.String())
	}

	var data struct {
		Success        bool `json:"success"`
		FeatureCount   int  `json:"feature_count"`
		CompliantCount int  `json:"compliant_count"`
		FlaggedCount   int  `json:"flagged_count"`
		Parcels        []struct {
			ID     string    `json:"id"`
			Status string    `json:"status"`
			Coords []float64 `json:"coords"`
		} `json:"parcels"`
	}

	if err := json.Unmarshal(w.Body.Bytes(), &data); err != nil {
		t.Fatalf("failed to parse parcels validation response: %v", err)
	}

	if !data.Success || data.FeatureCount != 2 {
		t.Errorf("expected 2 features, got %d", data.FeatureCount)
	}
	if len(data.Parcels) != 2 {
		t.Errorf("expected 2 cleaned parcels, got %d", len(data.Parcels))
	}
}

func TestSensorEvaluate(t *testing.T) {
	// Smallholder plot < 0.5 ha should trigger fallback
	req := httptest.NewRequest(http.MethodGet, "/api/sensor/evaluate?ha=0.35", nil)
	w := httptest.NewRecorder()
	handleSensorEvaluate(w, req)

	if w.Result().StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK")
	}

	var data map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &data); err != nil {
		t.Fatalf("json parse error: %v", err)
	}

	if data["fallback_triggered"] != true {
		t.Errorf("expected fallback_triggered == true for 0.35 ha plot")
	}
	if data["selected_tier"] != "PlanetScope / NICFI (3m Analytic)" {
		t.Errorf("expected PlanetScope tier, got %v", data["selected_tier"])
	}
}

func TestTracesDirectSubmit(t *testing.T) {
	payload := `{"plot_id": "PLOT-CO-1049", "commodity": "Coffee", "status": "COMPLIANT", "ha": "0.35 ha"}`
	req := httptest.NewRequest(http.MethodPost, "/api/traces/direct-submit", bytes.NewBufferString(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handleTracesDirectSubmit(w, req)

	if w.Result().StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK")
	}

	var res map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("json parse error: %v", err)
	}

	if res["status"] != "ACCEPTED" {
		t.Errorf("expected status ACCEPTED for compliant plot, got %v", res["status"])
	}
	if !strings.HasPrefix(res["traces_reference"].(string), "26NL") {
		t.Errorf("expected EU reference code prefix 26NL, got %v", res["traces_reference"])
	}
}

func TestSAPPOVerify(t *testing.T) {
	// Compliant PO verification
	payload := `{"PurchaseOrder": "4500091240", "PurchaseOrderItem": "00010", "Vendor": "100492", "Status": "COMPLIANT"}`
	req := httptest.NewRequest(http.MethodPost, "/api/erp/sap/po-verify", bytes.NewBufferString(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handleSAPPOVerify(w, req)

	if w.Result().StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK")
	}

	var res map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("json parse error: %v", err)
	}

	decision := res["decision"].(map[string]interface{})
	if decision["sap_status"] != "APPROVED" {
		t.Errorf("expected sap_status APPROVED, got %v", decision["sap_status"])
	}
	if decision["goods_receipt_blocked"] != false {
		t.Errorf("expected goods_receipt_blocked == false")
	}

	// Violation PO verification (should block)
	payloadViol := `{"PurchaseOrder": "4500091241", "PurchaseOrderItem": "00010", "Vendor": "100492", "Status": "VIOLATION"}`
	reqViol := httptest.NewRequest(http.MethodPost, "/api/erp/sap/po-verify", bytes.NewBufferString(payloadViol))
	reqViol.Header.Set("Content-Type", "application/json")
	wViol := httptest.NewRecorder()
	handleSAPPOVerify(wViol, reqViol)

	var resViol map[string]interface{}
	_ = json.Unmarshal(wViol.Body.Bytes(), &resViol)
	decisionViol := resViol["decision"].(map[string]interface{})
	if decisionViol["sap_status"] != "BLOCKED" || decisionViol["goods_receipt_blocked"] != true {
		t.Errorf("expected sap_status BLOCKED and goods_receipt_blocked true")
	}
}

func TestOracleShipmentClearance(t *testing.T) {
	payload := `{"TransactionId": "GTM-TX-2026-9041", "PartyId": "PRTY-AGRI-BRAZIL", "ItemNumber": "COMM-COFFEE-01", "Status": "COMPLIANT"}`
	req := httptest.NewRequest(http.MethodPost, "/api/erp/oracle/shipment-clearance", bytes.NewBufferString(payload))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	handleOracleShipmentClearance(w, req)

	if w.Result().StatusCode != http.StatusOK {
		t.Fatalf("expected 200 OK")
	}

	var res map[string]interface{}
	if err := json.Unmarshal(w.Body.Bytes(), &res); err != nil {
		t.Fatalf("json parse error: %v", err)
	}

	gtm := res["gtm_screening_result"].(map[string]interface{})
	if gtm["screening_status"] != "PASSED" {
		t.Errorf("expected screening_status PASSED, got %v", gtm["screening_status"])
	}
	if gtm["dispatch_authorized"] != true {
		t.Errorf("expected dispatch_authorized == true")
	}
}

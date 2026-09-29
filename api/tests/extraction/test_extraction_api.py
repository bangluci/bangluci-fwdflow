from tests.documents import pdf_factory as factory

RESULT = {"bl_no": "HBL001", "carrier_name": "MAERSK", "pol": "CNSHA", "pod": "VNSGN", "vessel": "EVER A",
          "voyage": "12E", "total_packages": 10,
          "containers": [{"container_no": "CSQU3054383", "seal_no": "S9", "container_type": "40HC",
                          "gross_weight_kg": "100"}, {"container_no": "TGHU1234567", "seal_no": None,
                                                      "container_type": "20GP", "gross_weight_kg": None}]}


def test_get_extraction_returns_result_and_current_values(client, login_as, make_shipment, make_container,
                                                           make_extraction):
    login_as("DOCS")
    shipment = make_shipment(hbl_no="OLD-HBL", vessel="OLD VESSEL")
    make_container(shipment, container_no="CSQU3054383", seal_no="S1")
    extraction = make_extraction(shipment=shipment, status="REVIEW", result=RESULT, field_issues=[])
    data = client.get(f"/api/extractions/{extraction.id}").json()["data"]
    assert data["status"] == "REVIEW" and data["result"]["bl_no"] == "HBL001" and data["version"] == 1
    current = data["current"]
    assert current["/bl_no"] == "OLD-HBL" and current["/vessel"] == "OLD VESSEL" and current["/voyage"] is None
    assert current["/pol"] == "CNSHA" and current["/pod"] == "VNSGN" and current["/carrier_name"] == "Maersk"
    assert current["/containers/0"]["seal_no"] == "S1" and current["/containers/1"] is None
    assert data["document"]["mime"] == "application/pdf" and data["document"]["page_count_rendered"] == 1


def test_current_values_use_mbl_for_master_bill(client, login_as, make_shipment, make_extraction, make_document):
    login_as("DOCS")
    shipment = make_shipment(mbl_no="MAEU999", hbl_no="H1")
    extraction = make_extraction(document=make_document(shipment, "MBL"), result=RESULT, status="REVIEW")
    assert client.get(f"/api/extractions/{extraction.id}").json()["data"]["current"]["/bl_no"] == "MAEU999"


def test_lcl_shipment_has_no_container_current_values(client, login_as, make_shipment, make_extraction):
    login_as("DOCS")
    extraction = make_extraction(shipment=make_shipment(load_type="LCL"), status="REVIEW", result=RESULT)
    current = client.get(f"/api/extractions/{extraction.id}").json()["data"]["current"]
    assert not [key for key in current if key.startswith("/containers")]


def test_page_image_is_jpeg(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    upload = client.post(f"/api/shipments/{shipment.id}/documents",
                         files={"file": ("a.pdf", factory.simple_pdf(2), "application/pdf")}, data={"doc_type": "HBL"})
    extraction_id = upload.json()["data"]["extraction_id"]
    res = client.get(f"/api/extractions/{extraction_id}/pages/2")
    assert res.status_code == 200 and res.headers["content-type"] == "image/jpeg"
    assert res.content.startswith(b"\xff\xd8\xff") and res.headers["cache-control"] == "private, no-store"


def test_page_out_of_range_404(client, login_as, make_shipment):
    login_as("DOCS")
    shipment = make_shipment()
    upload = client.post(f"/api/shipments/{shipment.id}/documents",
                         files={"file": ("a.pdf", factory.simple_pdf(1), "application/pdf")}, data={"doc_type": "HBL"})
    extraction_id = upload.json()["data"]["extraction_id"]
    assert client.get(f"/api/extractions/{extraction_id}/pages/0").status_code == 404
    assert client.get(f"/api/extractions/{extraction_id}/pages/2").status_code == 404


def test_missing_extraction_404(client, login_as):
    login_as("DOCS")
    assert client.get("/api/extractions/999999").status_code == 404


def test_accountant_and_customer_forbidden(client, login_as, make_extraction):
    extraction = make_extraction(status="REVIEW", result=RESULT)
    login_as("ACCOUNTANT")
    assert client.get(f"/api/extractions/{extraction.id}").status_code == 403
    client.cookies.clear()
    login_as("CUSTOMER")
    assert client.get(f"/api/extractions/{extraction.id}").status_code == 403

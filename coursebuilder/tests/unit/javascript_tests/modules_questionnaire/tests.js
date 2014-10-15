describe("questionnaire library", function () {

  beforeEach(function () {
    jasmine.getFixtures().fixturesPath = "base/";
    loadFixtures("tests/unit/javascript_tests/modules_questionnaire/" +
        "fixture.html");
    this.payload = JSON.parse(readFixtures(
        "tests/unit/javascript_tests/modules_questionnaire/form_data.json"));
    this.form = $("#standard-form form");
    this.key = "This-form-id"
    cbShowMsg = jasmine.createSpy("cbShowMsg");
    cbShowMsgAutoHide = jasmine.createSpy("cbShowMsgAutoHide");
  });

  it("populates the form from JSON blob", function() {
    setFormData(this.payload.form_data || {}, this.key);

    expect($(this.form).find("[name='fname']").val()).toEqual("A. Student");
    expect($(this.form).find("[name='age']").val()).toEqual("100");
    expect($(this.form).find("[name='date']").val()).toEqual("2014-09-17");
    expect($(this.form).find("[name='color']").val()).toEqual("#000000");
    expect($(this.form).find("[name='week']").val()).toEqual("2014-W37");
    expect($(this.form).find("[name='datetime']").val())
        .toEqual("test-date-time");
    expect($(this.form).find("[name='local']").val())
        .toEqual("2014-09-11T14:21");
    expect($(this.form).find("[name='month']").val()).toEqual("2014-09");
    expect($(this.form).find("[name='email']").val())
        .toEqual("test@example.com");
    expect($(this.form).find("[name='range']").val()).toEqual("5");
    expect($(this.form).find("[name='search']").val()).toEqual("test-search");
    expect($(this.form).find("[name='url']").val())
        .toEqual("http://www.google.com");
    expect($(this.form).find("[name='tel']").val()).toEqual("012334545");
    expect($(this.form).find("[name='time']").val()).toEqual("12:02");
    expect($(this.form).find("[name='select']").val()).toEqual("Apple");
    expect($(this.form).find("[name='radio']").val()).toEqual("male");
    expect($(this.form).find("[name='datalist']").val()).toEqual("Peas");
    expect($(this.form).find("[name='textarea']").val()).toEqual("A student.");
    expect($(this.form).find("[name='checkbox']").val())
        .toEqual("Bike" || "Walk");
  });

  it("executes the correct logic when data status is 200", function() {
    setFormData(this.payload.form_data || {}, this.key);
    var data = ')]}\' {"status": 200, "message": "Response submitted"}';
    onAjaxPostFormData(data);
    expect(cbShowMsgAutoHide).toHaveBeenCalled();
  });

  it("shows an error message on failure", function() {
    setFormData(this.payload.form_data || {}, this.key);
    var data = ')]}\' {"status": 403, "message": "Permission denied"}';
    onAjaxPostFormData(data);
    expect(cbShowMsg).toHaveBeenCalled();
  });
});

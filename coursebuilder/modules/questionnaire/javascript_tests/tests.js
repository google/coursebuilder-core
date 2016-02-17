describe("questionnaire library", function () {

  beforeEach(function () {
    jasmine.getFixtures().fixturesPath = "base/";
    loadFixtures("modules/questionnaire/javascript_tests/fixture.html");
    this.payload = JSON.parse(readFixtures(
        "modules/questionnaire/javascript_tests/form_data.json"));
    this.button = $("button.questionnaire-button");
    this.form = $("#standard-form form");
    this.key = "This-form-id"
    cbShowMsg = jasmine.createSpy("cbShowMsg");
    cbShowMsgAutoHide = jasmine.createSpy("cbShowMsgAutoHide");
    $.ajax = jasmine.createSpy("$.ajax");
    gcbTagEventAudit = jasmine.createSpy("gcbTagEventAudit");
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
    var postMessageDiv = $(this.button).parent().find("div.post-message");

    setFormData(this.payload.form_data || {}, this.key);
    expect(postMessageDiv.hasClass("hidden")).toBe(true);
    var data = ')]}\' {"status": 200, "message": "Response submitted"}';
    onAjaxPostFormData(data, this.button);
    expect(cbShowMsgAutoHide).toHaveBeenCalled();
    expect(postMessageDiv.hasClass("hidden")).toBe(false);
  });

  it("shows an error message on failure", function() {
    var postMessageDiv = $(this.button).parent().find("div.post-message");
    setFormData(this.payload.form_data || {}, this.key);
    var data = ')]}\' {"status": 403, "message": "Permission denied"}';
    onAjaxPostFormData(data, this.button);
    expect(cbShowMsg).toHaveBeenCalled();
    expect(postMessageDiv.hasClass("hidden")).toBe(true);
  });

  it("Send the right AJAX data", function() {
    setFormData(this.payload.form_data || {}, this.key);
    onSubmitButtonClick(this.key, "my-xsrf-token", this.button);

    expect($.ajax).toHaveBeenCalled();
    expect($.ajax.calls.mostRecent().args.length).toBe(1);
    var ajaxArg = $.ajax.calls.mostRecent().args[0];
    expect(ajaxArg.type).toBe("POST");
    expect(ajaxArg.url).toBe("rest/modules/questionnaire");
    expect(ajaxArg.dataType).toBe("text");
    expect(ajaxArg.data.request).toBe(JSON.stringify({
      xsrf_token: "my-xsrf-token",
      key: this.key,
      payload: {
        form_data: this.payload.form_data
      }
    }));

    expect(gcbTagEventAudit).toHaveBeenCalledWith({
      key: this.key,
      form_data: this.payload.form_data
    }, "questionnaire");
  });

  function expectDisabled(form, isDisabled) {
    form.find('input,select,textarea').each(function() {
      expect($(this).prop("disabled")).toBe(isDisabled);
    });
  }

  it("can disable the form", function() {
    setFormData(this.payload.form_data || {}, this.key);
    expectDisabled(this.form, false);
    disableForm(this.button, this.key);
    expectDisabled(this.form, true);
  });

  it("can require single submission", function() {
    var payloadJson = readFixtures(
        "modules/questionnaire/javascript_tests/form_data.json");
    var data = ")]}'" + JSON.stringify({
      status: 200,
      payload: payloadJson
    });

    // Empty form, multiple submissions allowed, expect enabled
    onAjaxGetFormData("[]", this.key, this.button, false);
    expectDisabled(this.form, false);
    // Populated form, multiple submissions allowed, expect enabled
    onAjaxGetFormData(data, this.key, this.button, false);
    expectDisabled(this.form, false);

    // Empty form, multiple submissions disllowed, expect enabled
    onAjaxGetFormData("[]", this.key, this.button, true);
    expectDisabled(this.form, false);
    // Populated form, multiple submissions disallowed, expect disabled
    onAjaxGetFormData(data, this.key, this.button, true);
    expectDisabled(this.form, true);
  });
});

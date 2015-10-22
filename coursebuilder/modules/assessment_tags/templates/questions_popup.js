$(function() {
  var _env = cb_global;
  var _showMsgAutoHide = cbShowMsgAutoHide;
  var _showMsg = cbShowMsg;

  var _GENERIC_QUESTION_REST_HANDLER = 'rest/question/all';
  var _HANDLER_URL_TABLE = {
    'mc_tab': 'rest/question/mc',
    'sa_tab': 'rest/question/sa'
  };
  var EDIT_TAB_LABEL = 'Edit';
  var CREATE_MC_TAB_LABEL = 'Create Multiple Choice';
  var CREATE_SA_TAB_LABEL = 'Create Short Answer';
  var SELECT_EXISTING_TAB_LABEL = 'Select Existing';
  var CHANGE_QUESTION_TAB_LABEL = 'Change Question';

  var tabBar = $(
    '<div class="mdl-tabs__tab-bar">' +
    '  <a id="mc_tab" class="mdl-tabs__tab"></a>' +
    '  <a id="sa_tab" class="mdl-tabs__tab"></a>' +
    '  <a id="select_tab" class="mdl-tabs__tab"></a>' +
    '</div>'
  );
  var xsrfTokenTable;

  function parseAjaxResponse(s) {
    var xssiPrefix = ")]}'";
    return JSON.parse(s.replace(xssiPrefix, ''));
  }

  function getFormData(quid) {
    var weight = _env.form.getFieldByName('weight').getValue();

    return $.ajax({
      type: 'GET',
      url: _GENERIC_QUESTION_REST_HANDLER,
      data: {key: quid},
      dataType: 'text'
    }).then(function(data) {
      populateForm(data, weight);
    });
  }

  function populateForm(data, weight) {
    data = parseAjaxResponse(data);
    if (data.status != 200) {
      _showMsg(data.message);
      return;
    }
    xsrfTokenTable = JSON.parse(data.xsrf_token);

    var payload = JSON.parse(data['payload']);
    _env.form.setValue(payload);
    _env.form.getFieldByName('weight_holder').setValue({weight: weight});

    // InputEx sets invalid field class on load but we want this only on submit
    $('.inputEx-invalid').removeClass('inputEx-invalid');

    tabBar.find('a').show().removeClass('is-active');
    $('#cb-oeditor-form .mdl-tabs__panel').removeClass('is-active');

    var quType = _env.form.getFieldByName('qu_type').getValue();
    if (quType == 'mc') {
      $('#mc_tab').text(EDIT_TAB_LABEL).addClass('is-active');
      $('#sa_tab').hide();
      $('#select_tab').text(CHANGE_QUESTION_TAB_LABEL);
      $('#cb-oeditor-form .mc-container').addClass('is-active');
      mcUpdateToggleFeedbackButtons(_env.form.getFieldByName('mc_tab'));
    } else if (quType == 'sa') {
      $('#mc_tab').hide();
      $('#sa_tab').text(EDIT_TAB_LABEL).addClass('is-active');
      $('#select_tab').text(CHANGE_QUESTION_TAB_LABEL);
      $('#cb-oeditor-form .sa-container').addClass('is-active');
      saUpdateToggleFeedbackButtons(_env.form.getFieldByName('sa_tab'));
    } else {
      $('#mc_tab').text(CREATE_MC_TAB_LABEL).addClass('is-active');
      $('#sa_tab').text(CREATE_SA_TAB_LABEL);
      $('#select_tab').text(SELECT_EXISTING_TAB_LABEL);
      $('#cb-oeditor-form .mc-container').addClass('is-active');
    }

    // Run MDL registration again
    window.componentHandler.upgradeAllRegistered()
  }

  function validateFormData() {
    // Validate only the form fields in the selected tab
    var activeTab = tabBar.find('.is-active').attr('id');
    return _env.form.getFieldByName(activeTab).validate();
  }

  function saveFormData() {
    var finishSave = $.Deferred();
    var activeTab = tabBar.find('.is-active').attr('id');

    if (activeTab == 'select_tab') {
      _env.form.getFieldByName('quid').setValue(_env.form
          .getFieldByName('select_tab').getFieldByName('quid').getValue());
      return true;
    }

    setQuestionDescriptionIfEmpty(_env.form.getFieldByName(activeTab));

    var handlerUrl = _HANDLER_URL_TABLE[activeTab];
    var xsrfToken = xsrfTokenTable[activeTab];
    var formData = _env.form.getValue();

    var requestDict = {
      xsrf_token: xsrfToken,
      key: formData.quid || '',
      payload: JSON.stringify(formData[activeTab])
    };
    $.ajax({
      type: 'PUT',
      url: handlerUrl,
      data: {'request': JSON.stringify(requestDict)},
      dataType: 'text'
    }).then(function(data) {
      onFormDataSaved(data, finishSave);
    });
    return finishSave;
  }

  function onFormDataSaved(data, finishSave) {
    data = parseAjaxResponse(data);
    if (data.status != 200) {
      _showMsg(data.message);
      return;
    }
    _showMsgAutoHide(data.message);

    var key = JSON.parse(data.payload).key;
    _env.form.getFieldByName('quid').setValue(key);

    // Copy the weight into its top-level field
    var weight = _env.form.getFieldByName('weight_holder').getValue().weight;
    _env.form.getFieldByName('weight').setValue(weight);

    finishSave.resolve();
  }

  function makeTabBar() {
    $('#formContainer > .inputEx-Group')
        .addClass('mdl-tabs mdl-js-tabs mdl-js-ripple-effect')
        .prepend(tabBar);

    // Connect the tabs to the panes
    var tabClasses = [
      'mc-container',
      'sa-container',
      'select-container'
    ];
    $.each(tabClasses, function(index, className) {
      var container = $('#cb-oeditor-form .' + className);
      container.addClass('mdl-tabs__panel');
      tabBar.find('a').eq(index).attr('href', '#' + container.get(0).id);
    });
  }

  function bindSelect() {
    $('#cb-oeditor-form select[name="quid"]').change(function() {
      getFormData($(this).val());
    });
  }

  function initQuestionsPopup() {
    var formData = _env.form.getValue();
    makeTabBar();
    bindSelect();
    getFormData(formData.quid).then(function() {
        initMcQuestionEditor(_env.form.getFieldByName('mc_tab'));
        initSaQuestionEditor(_env.form.getFieldByName('sa_tab'));
        _env.lastSavedFormValue = _env.form.getValue();
    });
    _env.validate = validateFormData;
    _env.onSaveClick = saveFormData;
  }

  initQuestionsPopup();
});

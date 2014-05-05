event_payloads.json contains one root object whose properties represent payloads
emitted from gcbAudit in the activity-generic javascript file. Each payload has
four properties:
1) event_data - the data_dict object
2) event_source - a string describing the source of the event
3) event_async - a boolean describing whether or not the event is submitted
                 asynchronously
4) transformed_dict_list - the expected value of the dictionary that this event
                           should generate when it is summarized in the backend
                           for analytics aggregation.

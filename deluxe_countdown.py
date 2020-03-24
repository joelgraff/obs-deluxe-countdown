#-----------------------------------------------------------------------
# Copyright (C) 2020 by Joel Graff <monograff76@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#-----------------------------------------------------------------------

"""
Enhanced countdown script for use with OBS, based on lua-based
script included with OBS.

https://github.com/obsproject/obs-studio/blob/b2302902a3b3e1cce140a6417f4c5e490869a3f2/UI/frontend-plugins/frontend-tools/data/scripts/countdown.lua
"""

import datetime
import time
from types import SimpleNamespace
from copy import deepcopy

import obspython as obs

class Clock():
    """
    Class to manage the current clock state
    """

    def __init__(self):
        """
        Constructor
        """

        self.reference_time = None
        self.target_time = None
        self.duration = None
        self.mode ='duration'

    def reset(self):
        """
        Reset the clock - only effective for
        """

        self.reference_time = datetime.datetime.now()

    def get_time(self):
        """
        Get the countdown time as a string
        """

        _current_time = datetime.datetime.now()
        _result = None

        #calculate string of the time remaining since the timer was reset
        if self.mode == 'duration':
            _delta = _current_time - self.reference_time
            _duration = datetime.timedelta(seconds=self.duration)

            if _delta > _duration:
                return None

            _result = str(_duration - _delta).split(':')

        #calculate string of the time remaining until the target time is reached
        elif self.target_time is None:
            return "00:00:00"

        elif self.target_time < _current_time:
            return "00:00:00"

        else:
            _result = str(self.target_time - _current_time).split(':')

        #formatting to pad missing zeros
        _days_hours = _result[0].split(',')

        if len(_days_hours) > 1:
            _result = _days_hours[1:] + _result[1:]

        _result[-1] = str(int(round(float(_result[-1]), 0)))
        _result = ['{:02d}'.format(int(_v)) for _v in _result]
        _result = ':'.join(_result)

        if len(_days_hours) > 1:
            if _days_hours[0][0:2] != '-1':
                _result = _days_hours[0] + ', ' + _result

        return _result

    def set_duration(self, interval):
        """
        Set the duration of the timer
        """

        self.mode = 'duration'
        self.duration = self.update_duration(interval)

    def set_date_time(self, target_date, target_time):
        """
        Set the target date / time of the timer
        """

        self.mode = 'date/time'

        try:
            self.duration = self.update_date_time(target_date, target_time)
        except:
            self.duration = 0

    def update_duration(self, interval):
        """
        Calculate the number of seconds for the specified duration
        Format may be:
        - Integer in minutes
        - HH:MM:SS as a string
        """

        interval = interval.split(':')[-3:]
        _seconds = 0

        #Only one element - duration specified in minutes
        if len(interval) == 1:

            if not interval[0]:
                interval[0] = 0

            return float(interval[0]) * 60.0

        #otherwise, duration in HH:MM:SS format
        for _i, _v in enumerate(interval[::-1]):\

            if not _v:
                continue

            _m = 60 ** _i
            _seconds += int(_v) * _m

        return _seconds

    def update_date_time(self, target_date, target_time):
        """
        Set the target date and time
        """

        if target_time is None:
            return

        #test for 12-hour format specification
        _am_pm = target_time.find('am')
        _is_pm = False

        if _am_pm == -1:
            _am_pm = target_time.find('pm')
            _is_pm = _am_pm > -1

        #strip 'am' or 'pm' text
        if _am_pm != -1:
            target_time = target_time[:_am_pm]

        target_time = [int(_v) for _v in target_time.split(':')]

        if len(target_time) == 2:
            target_time += [0]

        #adjust 12-hour pm to 24-hour format
        if _is_pm:
            if target_time[0] < 12:
                target_time[0] += 12

        elif target_time[0] == 12:
                target_time[0] = 0

        if target_time[0] > 23:
            target_time[0] = 0

        _target = None
        _now = datetime.datetime.now()

        #calculate date
        if target_date == 'TODAY':
            target_date = [_now.month, _now.day, _now.year]

        else:
            target_date = [int(_v) for _v in target_date.split('/')]

        self.target_time = datetime.datetime(
                target_date[2], target_date[0], target_date[1],
                target_time[0], target_time[1], target_time[2]
        )

class State():
    """
    Script state class
    """

    def __init__(self):
        """
        Constructor
        """

        #constants
        self.OBS_COMBO = obs.OBS_COMBO_TYPE_LIST
        self.OBS_TEXT = obs.OBS_TEXT_DEFAULT
        self.OBS_BUTTON = 'OBS_BUTTON'

        #other global vars for OBS callbacks
        self.clock = Clock()
        self.hotkey_id = 0
        self.activated = False
        self.properties = self.build_properties()

    def build_properties(self):
        """
        Build dict defining script properties
        """

        #lambda to return a SimpleNamespace object for OBS data properties
        _fn = lambda p_name, p_default, p_type, p_items=None:\
            SimpleNamespace(
                name=p_name, default=p_default, type=p_type, items= p_items,
                cur_value=p_default)

        _p = {}

        _p['interval_type'] = _fn(
            'Interval Type', 'Duration', self.OBS_COMBO,
            ['Duration', 'Date/Time']
        )

        _p['duration'] = _fn('Duration', '0', self.OBS_TEXT)
        _p['date'] = _fn('Date', 'TODAY', self.OBS_TEXT)
        _p['time'] = _fn('Time', '12:00:00 pm', self.OBS_TEXT)
        _p['end_text'] = _fn('End Text', 'Live Now!', self.OBS_TEXT)

        _p['text_source'] =\
            _fn('Text Source', '', self.OBS_COMBO, self.get_source_list())

        return _p

    def get_source_list(self):
        """
        Get list of text sources
        """

        _sources = obs.obs_enum_sources()
        _names = []

        if _sources is not None:

            for _source in _sources:

                _source_id = obs.obs_source_get_unversioned_id(_source)

                if _source_id == "text_gdiplus"\
                    or _source_id == "text_ft2_source":

                    _names.append(obs.obs_source_get_name(_source))

        return _names

    def get_value(self, source_name, settings=None):
        """
        Get the value of the source using the provided settings
        If settings is None, previously-provided settings will be used
        """

        if settings:
            _value = obs.obs_data_get_string(settings, source_name)
            self.properties[source_name].cur_value = _value

            return obs.obs_data_get_string(settings, source_name)

        return self.properties[source_name].cur_value

    def set_value(self, source_name, prop, value):
        """
        Set the value of the source using the provided settings
        If settings is None, previously-provided settings will be used
        """

        _settings = obs.obs_data_create()
        _source = obs.obs_get_source_by_name(source_name)

        obs.obs_data_set_string(_settings, prop, value)
        obs.obs_source_update(_source, _settings)
        obs.obs_data_release(_settings)
        obs.obs_source_release(_source)

        self.properties[source_name].cur_value = value

script_state = State()

#-----------------------
# OBS callback functions
#-----------------------

def update_text():
    """
    Update the text with the passed time string
    """

    _time = script_state.clock.get_time()

    if not _time:
        obs.remove_current_callback()

    _source = script_state.get_value('text_source')

    if not _source:
        return

    if _time is None or _time == "00:00:00":
        _time = script_state.get_value('end_text')

    _settings = obs.obs_data_create()
    _source = obs.obs_get_source_by_name(_source)

    obs.obs_data_set_string(_settings, 'text', _time)
    obs.obs_source_update(_source, _settings)
    obs.obs_data_release(_settings)
    obs.obs_source_release(_source)

def activate(activating):
    """
    Activate / deactivate timer based on source text object state
    """

    #if already active, return
    if script_state.activated == activating:
        return

    script_state.activated = activating

    #add the timer if becoming active
    if activating:

        update_text()
        obs.timer_add(update_text, 1000)

    #remove if going inactive
    else:
        obs.timer_remove(update_text)

def activate_signal(cd, activating):
    """
    Called when source is activated / deactivated
    """
    _source = obs.calldata_source(cd, "text_source")

    if _source:

        _name = obs.obs_source_get_name(_source)
        if (_name == _name):
            activate(activating)

def source_activated(cd):
    """
    Signal callback for activation
    """

    activate_signal(cd, True)

def source_deactivated(cd):
    """
    Signal callback for de-activation
    """

    activate_signal(cd, False)

def reset():
    """
    Reset the timer
    """

    activate(False)

    _source_name = script_state.get_value('text_source')
    _source = obs.obs_get_source_by_name(_source_name)

    if _source:
        _active = obs.obs_source_active(_source)
        obs.obs_source_release(_source)
        activate(_active)

    script_state.clock.reset()
    update_text()

def reset_button_clicked(props, p):
    """
    Callback for the reset button
    """

    reset()
    return False

def script_update(settings):
    """
    Called when the user updates settings
    """

    activate(False)

    _type = obs.obs_data_get_string(settings, 'interval_type')

    if _type == 'Duration':
        _interval = obs.obs_data_get_string(settings, 'duration')
        script_state.clock.set_duration(_interval)

    else:
        _date = obs.obs_data_get_string(settings, 'date')
        _time = obs.obs_data_get_string(settings, 'time')
        script_state.clock.set_date_time(_date, _time)

    #update the current value in the properties
    for _key, _item in script_state.properties.items():
        _item.cur_value = obs.obs_data_get_string(settings, _key)

    script_state.clock.reset()
    update_text()

    activate(True)

def script_description():
    """
    Script description
    """
    return """
    Countdown clock for a duration or to a date/time.\n
    Interval Type\tDuration or Time
    Duration\tInteger (sec) or HH:MM:SS
    Date\t\tMM/DD/YYYY or TODAY
    Time\t\tHH:MM:SS [am/pm] for 12-hour
    Start\End Text\tShown during/after countdown
    Text Source\tSource for start / end text
    """

def script_defaults(settings):
    """
    Set default values for properties
    """

    for _k, _v in script_state.properties.items():

        if _v.type != script_state.OBS_BUTTON:
            obs.obs_data_set_default_string(settings, _k, _v.default)

    for _k, _v in script_state.properties.items():

        if _v.type != script_state.OBS_BUTTON:
            _v.cur_value = obs.obs_data_get_string(settings, _k)

    if script_state.properties['interval_type'] == 'Duration':

        script_state.clock.set_duration(
            script_state.properties['duration'].cur_value)

    else:

        script_state.clock.set_date_time(
            script_state.properties['date'].cur_value,
            script_state.properties['time'].cur_value
        )

def script_properties():
    """
    Create properties for script settings dialog
    """

    props = obs.obs_properties_create()

    for _k, _v in script_state.properties.items():

        if _v.type == script_state.OBS_COMBO:

            _p = obs.obs_properties_add_list(
                props, _k, _v.name, _v.type, obs.OBS_COMBO_FORMAT_STRING)

            for _item in _v.items:
                obs.obs_property_list_add_string(_p, _item, _item)

        else:

            obs.obs_properties_add_text(props, _k, _v.name, _v.type)

    obs.obs_properties_add_button(
        props, 'reset', 'Reset', reset_button_clicked)

    return props

def script_save(settings):
    """
    Save state for script
    """

    _hotkey_save_array = obs.obs_hotkey_save(script_state.hotkey_id)
    obs.obs_data_set_array(settings, "reset_hotkey", _hotkey_save_array)
    obs.obs_data_array_release(_hotkey_save_array)

def script_load(settings):
    """
    Connect hotkey and activation/deactivation signal callbacks
    """

    _sh = obs.obs_get_signal_handler()
    obs.signal_handler_connect(_sh, "source_activate", source_activated)
    obs.signal_handler_connect(_sh, "source_deactivate", source_deactivated)

    _hotkey_id = obs.obs_hotkey_register_frontend(
        "reset_timer_thingy", "Reset Timer", reset)

    _hotkey_save_array = obs.obs_data_get_array(settings, "reset_hotkey")
    obs.obs_hotkey_load(_hotkey_id, _hotkey_save_array)
    obs.obs_data_array_release(_hotkey_save_array)

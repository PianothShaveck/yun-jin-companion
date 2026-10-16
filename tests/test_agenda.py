"""Real SQLite recurrence, DST, recovery and notification state-machine tests."""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from yun_jin_data import Store
import yun_jin_agenda as agenda


class AgendaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name)
        self.a=agenda.AgendaStore(self.store)
        original_zone=agenda._zone
        self.system_zone='Europe/Rome'
        self.zone=patch.object(agenda,'_zone',side_effect=lambda name='':original_zone(name or self.system_zone))
        self.zone.start()
        self.now=self.ts('2026-10-16T07:00:00')

    def tearDown(self):
        self.zone.stop();self.store.close();self.tmp.cleanup()

    def ts(self,value,zone=''):
        return agenda.wall_timestamp(value,zone)

    def reopen(self):
        self.store.close();self.store=Store(self.tmp.name);self.a=agenda.AgendaStore(self.store)

    def event(self,**kwargs):
        defaults=dict(title='Prova',start='2026-10-16T09:00:00',now=self.now)
        defaults.update(kwargs)
        return self.a.save_event(**defaults)

    def test_migration_keeps_existing_data_and_backup_contains_agenda(self):
        self.store.save_note('中文','你好');self.store.add_reminder('Vecchio',self.now)
        self.store.set_preference('volume',.31)
        alarm=self.a.save_alarm('Piano','08:00',weekdays=[0,2,4],now=self.now)
        event=self.event()
        self.reopen()
        self.assertEqual(self.store.notes()[0]['body'],'你好')
        self.assertEqual(self.store.reminders()[0]['title'],'Vecchio')
        self.assertEqual(self.store.preference('volume',0),.31)
        self.assertEqual(self.a.get(alarm)['weekdays'],[0,2,4])
        self.assertEqual(self.a.get(event)['title'],'Prova')
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.store.export_backup(Path(self.tmp.name)/'backup.zip')
        import sqlite3,zipfile
        from contextlib import closing
        with zipfile.ZipFile(Path(self.tmp.name)/'backup.zip') as z:
            z.extract('companion.sqlite3',Path(self.tmp.name)/'snapshot')
        with closing(sqlite3.connect(Path(self.tmp.name)/'snapshot/companion.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agenda_items').fetchone()[0],2)

    def test_once_alarm_next_day_explicit_date_and_auto_disable_rearm(self):
        alarm=self.a.save_alarm('', '06:30',now=self.now)
        self.assertEqual(self.a.get(alarm)['title'],'Sveglia')
        self.assertEqual(self.a.get(alarm)['on_date'],'2026-10-17')
        due=self.ts('2026-10-17T06:30:00')
        self.assertEqual(self.a.alarms(self.now)[0]['next_at'],due)
        alerts=self.a.poll(due)
        self.assertEqual(len(alerts),1);self.assertFalse(self.a.get(alarm)['enabled'])
        self.a.set_enabled(alarm,True,now=due+10)
        self.assertEqual(self.a.alarms(due+10)[0]['next_at'],due+86400)
        with self.assertRaisesRegex(ValueError,'future'):
            self.a.save_alarm('Passata','06:00',on_date='2026-10-16',now=self.now)
        future=self.a.save_alarm('Concerto','22:30',on_date='2026-11-21',now=self.now)
        self.assertEqual(self.a.get(future)['on_date'],'2026-11-21')

    def test_weekday_alarms_stay_local_and_disable_cancels_pending(self):
        alarm=self.a.save_alarm('Lezione','08:00',weekdays=[0,2,4],now=self.now)
        monday=self.ts('2026-10-19T08:00:00')
        self.assertEqual(self.a.next_occurrence(alarm,self.now+7200)['start'],monday)
        self.assertEqual(self.a.poll(monday)[0]['title'],'Lezione')
        self.a.set_enabled(alarm,False,now=monday+10)
        self.assertEqual(self.a.pending_alerts(),[])
        self.assertIsNone(self.a.alarms(monday)[0]['next_at'])
        self.assertEqual(self.a.poll(monday+20),[])

    def test_reenabled_recurring_alarm_does_not_backfill_disabled_days(self):
        alarm=self.a.save_alarm('Lezione','08:00',weekdays=list(range(7)),now=self.now)
        self.a.set_enabled(alarm,False,now=self.now)
        later=self.ts('2026-11-03T12:00:00')
        self.a.set_enabled(alarm,True,now=later)
        self.assertEqual(self.a.poll(later),[])
        self.assertEqual(self.a.missed_alerts(),[])
        self.assertEqual(self.a.next_deadline(later),self.ts('2026-11-04T08:00:00'))
        self.assertEqual(len(self.a.poll(self.ts('2026-11-04T08:00:00'))),1)

    def test_recurrence_daily_weekly_count_and_inclusive_until(self):
        rule=agenda.normalize_recurrence({'frequency':'daily','interval':2,'count':3},datetime(2026,10,16,9))
        self.assertEqual(list(agenda.recurrence_dates(date(2026,10,16),rule,date(2026,10,1),date(2026,11,1))),
                         [date(2026,10,n) for n in (16,18,20)])
        # Friday anchor, but a Monday/Wednesday rule starts the following week.
        rule=agenda.normalize_recurrence({'frequency':'weekly','interval':2,'weekdays':[0,2],'count':3},datetime(2026,10,16,9))
        self.assertEqual(list(agenda.recurrence_dates(date(2026,10,16),rule,date(2026,10,1),date(2026,12,1))),
                         [date(2026,10,26),date(2026,10,28),date(2026,11,9)])
        rule=agenda.normalize_recurrence({'frequency':'daily','until':'2026-10-18'},datetime(2026,10,16,9))
        self.assertEqual(len(list(agenda.recurrence_dates(date(2026,10,16),rule,date(2026,10,1),date(2026,11,1)))),3)

    def test_month_end_leap_day_and_count_count_actual_dates(self):
        rule={'frequency':'monthly','interval':1,'count':4}
        self.assertEqual(list(agenda.recurrence_dates(date(2026,1,31),rule,date(2026,1,1),date(2027,1,1))),
                         [date(2026,m,31) for m in (1,3,5,7)])
        rule={'frequency':'yearly','interval':1,'count':3}
        self.assertEqual(list(agenda.recurrence_dates(date(2024,2,29),rule,date(2024,1,1),date(2035,1,1))),
                         [date(y,2,29) for y in (2024,2028,2032)])

    def test_named_timezones_and_dst_gap_fold_are_explicit(self):
        gap=self.ts('2026-03-29T02:30:00','Europe/Rome')
        self.assertEqual(agenda.local_datetime(gap,'Europe/Rome').isoformat(),'2026-03-29T03:30:00')
        first=self.ts('2026-10-25T02:30:00','Europe/Rome')
        self.assertEqual(agenda.local_datetime(first,'UTC').isoformat(),'2026-10-25T00:30:00')
        self.assertEqual(agenda.local_datetime(first+3600,'Europe/Rome').isoformat(),'2026-10-25T02:30:00')
        with self.assertRaises(ValueError):self.ts('2026-10-16T08:00:00','Not/A_Timezone')
        with self.assertRaises(ValueError):self.ts('2026-10-16T08:00:00','时区')

    def test_daily_wall_clock_and_all_day_duration_survive_both_dst_transitions(self):
        event=self.event(start='2026-03-28T09:00:00',recurrence={'frequency':'daily'},now=self.ts('2026-03-01T00:00:00'))
        entries=self.a.occurrences('2026-03-28','2026-03-31')
        self.assertEqual([x['start_local'][11:16] for x in entries],['09:00']*3)
        self.assertEqual(entries[1]['start']-entries[0]['start'],23*3600)
        self.assertEqual(entries[2]['start']-entries[1]['start'],24*3600)
        self.a.delete(event)
        self.event(start='2026-03-29',end='2026-03-30',all_day=True,reminder_minutes=None)
        self.event(start='2026-10-25',end='2026-10-26',all_day=True,reminder_minutes=None)
        spring=self.a.occurrences('2026-03-29','2026-03-30')[0]
        autumn=self.a.occurrences('2026-10-25','2026-10-26')[0]
        self.assertEqual(spring['end']-spring['start'],23*3600)
        self.assertEqual(autumn['end']-autumn['start'],25*3600)
        self.assertEqual(self.a.occurrences('2026-10-26','2026-10-27'),[])

    def test_fall_fold_alarm_fires_once_and_spring_gap_fires_after_gap(self):
        start=self.ts('2026-10-24T20:00:00')
        alarm=self.a.save_alarm('Cambio ora','02:30',weekdays=list(range(7)),now=start)
        fold=self.ts('2026-10-25T02:30:00')
        self.assertEqual(len(self.a.poll(fold)),1)
        self.assertEqual(self.a.poll(fold+3600),[])
        self.assertEqual(len([x for x in self.a.alerts(True) if x['item_id']==alarm]),1)
        self.a.delete(alarm)
        alarm=self.a.save_alarm('Primavera','02:30',weekdays=list(range(7)),now=self.ts('2026-03-28T20:00:00'))
        gap=self.ts('2026-03-29T02:30:00')
        self.assertEqual(self.a.poll(gap-1),[])
        self.assertEqual(self.a.poll(gap)[0]['item_id'],alarm)

    def test_timezone_change_replans_floating_alarm_without_duplicate_occurrence(self):
        from PyQt6.QtCore import QByteArray
        alarm=self.a.save_alarm('Viaggio','08:00',weekdays=list(range(7)),now=self.now)
        self.a.poll(self.now)
        self.assertEqual(self.a.next_deadline(self.now),self.ts('2026-10-16T08:00:00','Europe/Rome'))
        self.system_zone='America/New_York'
        with patch.object(agenda.QTimeZone,'systemTimeZoneId',return_value=QByteArray(b'America/New_York')):
            self.assertEqual(self.a.poll(self.now+1),[])
            due=self.ts('2026-10-16T08:00:00','America/New_York')
            self.assertEqual(self.a.next_deadline(self.now+1),due)
            self.assertEqual(self.a.poll(due)[0]['item_id'],alarm)
        self.system_zone='Europe/Rome'
        self.assertEqual(self.a.poll(due+1),[])
        self.assertEqual(len(self.a.pending_alerts()),1)

    def test_overlap_month_queries_and_named_zone_convert_to_local_calendar(self):
        self.event(start='2026-10-31T23:30:00',end='2026-11-01T01:00:00')
        self.assertEqual(len(self.a.occurrences('2026-10-01','2026-11-01')),1)
        self.assertEqual(len(self.a.occurrences('2026-11-01','2026-12-01')),1)
        self.event(title='New York',start='2026-11-01T23:30:00',timezone='America/New_York')
        self.assertEqual(len(self.a.occurrences('2026-11-02','2026-11-03')),1)
        self.assertEqual(len(self.a.occurrences('2026-11-03','2026-11-04')),0)

    def test_single_move_cancel_and_series_metadata_preserve_exceptions(self):
        event=self.event(recurrence={'frequency':'weekly','weekdays':[4]})
        key='2026-10-23T09:00:00'
        self.a.save_exception(event,key,title='Spostata',start_local='2026-11-02T11:00:00',end_local='2026-11-02T12:30:00',color='teal')
        october=self.a.occurrences('2026-10-01','2026-11-01')
        self.assertEqual([x['start_local'] for x in october],['2026-10-16T09:00:00','2026-10-30T09:00:00'])
        moved=[x for x in self.a.occurrences('2026-11-01','2026-11-03') if x['title']=='Spostata'][0]
        self.assertEqual(moved['occurrence_key'],key);self.assertTrue(moved['exception']);self.assertEqual(moved['color'],'teal')
        self.a.save_event('Nome serie',start='2026-10-16T09:00:00',recurrence={'frequency':'weekly','weekdays':[4]},event_id=event,now=self.now)
        self.assertEqual(self.a.occurrences('2026-11-01','2026-11-03')[0]['title'],'Spostata')
        self.a.delete(event,key)
        self.assertEqual(self.a.occurrences('2026-11-01','2026-11-03'),[])
        with self.assertRaises(ValueError):self.a.save_exception(event,'2026-10-22T09:00:00',title='Wrong weekday')
        self.a.save_event('Nuovo orario',start='2026-10-16T10:00:00',recurrence={'frequency':'weekly','weekdays':[4]},event_id=event,now=self.now)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM agenda_exceptions').fetchone()[0],0)

    def test_notification_deadline_mute_flags_and_no_early_alert(self):
        event=self.event(voice=False,reminder_minutes=15)
        due=self.ts('2026-10-16T08:45:00')
        self.assertEqual(self.a.next_deadline(self.now),due)
        self.assertEqual(self.a.poll(due-1),[])
        alert=self.a.poll(due)[0]
        self.assertEqual(alert['item_id'],event);self.assertFalse(alert['voice']);self.assertFalse(alert['restored'])
        self.assertEqual(self.a.poll(due+1),[])
        self.assertEqual(self.a.poll(due-10),[])
        self.assertEqual(self.a.poll(due+2),[])
        self.a.dismiss(alert['id'])
        self.assertEqual(self.a.pending_alerts(),[])

    def test_notification_none_can_be_enabled_for_a_single_exception(self):
        event=self.event(reminder_minutes=None,recurrence={'frequency':'daily'})
        self.a.save_exception(event,'2026-10-17T09:00:00',reminder_minutes=30)
        due=self.ts('2026-10-17T08:30:00')
        self.assertEqual(self.a.next_deadline(self.now),due)
        self.assertEqual(self.a.poll(due)[0]['item_id'],event)
        self.assertEqual(self.a.poll(self.ts('2026-10-18T09:00:00')),[])

    def test_modified_reminder_does_not_hide_regular_next_notification(self):
        event=self.event(reminder_minutes=10,recurrence={'frequency':'daily'})
        self.a.save_exception(event,'2026-10-17T09:00:00',reminder_minutes=None)
        due=self.ts('2026-10-16T08:50:00')
        alert=self.a.poll(due)[0];self.a.dismiss(alert['id'])
        self.assertEqual(self.a.next_deadline(due+1),self.ts('2026-10-18T08:50:00'))
        self.a.save_exception(event,'2026-10-18T09:00:00',reminder_minutes=120)
        self.assertEqual(self.a.next_deadline(due+1),self.ts('2026-10-18T07:00:00'))

    def test_restart_restores_pending_silently_and_snooze_rings_once(self):
        self.a.save_alarm('Alzati','08:00',now=self.now)
        due=self.ts('2026-10-16T08:00:00')
        original=self.a.poll(due)[0]
        self.reopen()
        restored=self.a.poll(due+5)[0]
        self.assertEqual(restored['id'],original['id']);self.assertTrue(restored['restored'])
        snooze=self.a.snooze(restored['id'],5,now=due+5)
        self.reopen()
        self.assertEqual(self.a.poll(snooze-1),[])
        resumed=self.a.poll(snooze)[0]
        self.assertFalse(resumed['restored']);self.assertEqual(resumed['id'],original['id'])
        self.assertEqual(self.a.poll(snooze+1),[])
        self.a.dismiss(resumed['id'])
        self.reopen();self.assertEqual(self.a.poll(snooze+10),[])

    def test_seen_alert_stays_actionable_and_next_occurrence_supersedes_it(self):
        alarm=self.a.save_alarm('Mattina','08:00',weekdays=list(range(7)),now=self.now)
        due=self.ts('2026-10-16T08:00:00')
        alert=self.a.poll(due)[0]
        self.assertEqual(self.a.poll(due+3600),[])
        self.assertEqual(self.a.pending_alerts()[0]['id'],alert['id'])
        self.a.snooze(alert['id'],5,now=due+3600)
        self.assertEqual(self.a.poll(due+3900)[0]['id'],alert['id'])
        self.assertEqual(self.a.poll(due+86400)[0]['item_id'],alarm)
        self.assertEqual(len(self.a.pending_alerts()),1)
        self.assertEqual(self.a.missed_alerts()[0]['id'],alert['id'])

    def test_metadata_edit_preserves_snooze_and_never_reannounces_current_alarm(self):
        alarm=self.a.save_alarm('Mattina','08:00',weekdays=list(range(7)),now=self.now)
        due=self.ts('2026-10-16T08:00:00')
        alert=self.a.poll(due)[0]
        self.a.save_alarm('Nuovo titolo','08:00',weekdays=list(range(7)),alarm_id=alarm,now=due+5)
        self.assertEqual(self.a.poll(due+5),[])
        self.assertEqual(self.a.pending_alerts()[0]['title'],'Nuovo titolo')
        self.a.snooze(alert['id'],5,now=due+10)
        self.a.save_alarm('Ancora un titolo','08:00',weekdays=list(range(7)),alarm_id=alarm,now=due+20)
        self.assertEqual(self.a.poll(due+20),[])
        self.assertEqual(self.a.poll(due+310)[0]['title'],'Ancora un titolo')
        next_day=due+86400
        next_alert=self.a.poll(next_day)[0]
        self.a.snooze(next_alert['id'],5,now=next_day+10)
        self.a.save_alarm('Anche il giorno dopo','08:00',weekdays=list(range(7)),alarm_id=alarm,now=next_day+20)
        self.assertEqual(self.a.get(alarm)['start_local'],'2026-10-16T08:00:00')
        self.assertEqual(self.a.poll(next_day+310)[0]['title'],'Anche il giorno dopo')

    def test_single_occurrence_metadata_edit_preserves_pending_acknowledgement(self):
        event=self.event(recurrence={'frequency':'daily'})
        due=self.ts('2026-10-16T08:50:00')
        alert=self.a.poll(due)[0]
        self.a.save_exception(event,'2026-10-16T09:00:00',title='Titolo corretto')
        self.assertEqual(self.a.poll(due+10),[])
        self.assertEqual(self.a.pending_alerts()[0]['id'],alert['id'])
        self.assertEqual(self.a.pending_alerts()[0]['title'],'Titolo corretto')
        self.a.save_event('Nuovo titolo serie','2026-10-16T09:00:00',recurrence={'frequency':'daily'},event_id=event,now=due+20)
        self.assertEqual(self.a.poll(due+20),[])
        self.assertEqual(self.a.pending_alerts()[0]['title'],'Titolo corretto')

    def test_overdue_grace_and_long_absence_only_latest_missed_per_series(self):
        alarm=self.a.save_alarm('Mattina','08:00',weekdays=list(range(7)),now=self.now)
        event=self.event(recurrence={'frequency':'daily'})
        self.assertEqual(len(self.a.poll(self.ts('2026-10-16T08:09:59'))),1)
        later=self.ts('2026-11-04T20:00:00')
        self.assertEqual(self.a.poll(later),[])
        latest={x['item_id']:x for x in self.a.missed_alerts() if x['scheduled_at']>self.ts('2026-11-01T00:00:00')}
        self.assertEqual(set(latest),{alarm,event})
        self.assertEqual(len(self.a.missed_alerts()),3) # already announced alarm + latest each series
        self.assertTrue(all(x['state']=='missed' for x in latest.values()))
        self.assertEqual(self.a.poll(later+5),[])

    def test_ended_events_do_not_ring_even_within_notice_grace(self):
        self.event(start='2026-10-16T08:00:00',end='2026-10-16T08:05:00',reminder_minutes=0)
        self.assertEqual(self.a.poll(self.ts('2026-10-16T08:06:00')),[])
        self.assertEqual(len(self.a.missed_alerts()),1)

    def test_future_created_old_anchor_never_generates_historical_notice(self):
        self.event(start='2020-01-01T09:00:00',recurrence={'frequency':'daily'},now=self.now)
        self.assertEqual(self.a.poll(self.now),[])
        self.assertEqual(self.a.missed_alerts(),[])
        self.assertEqual(len(self.a.poll(self.ts('2026-10-16T08:50:00'))),1)

    def test_deleted_or_skipped_items_cannot_ring_and_cascade_history(self):
        event=self.event(recurrence={'frequency':'daily'})
        self.a.skip_occurrence(event,'2026-10-16T09:00:00')
        self.assertEqual(self.a.poll(self.ts('2026-10-16T08:50:00')),[])
        self.a.poll(self.ts('2026-10-17T08:50:00'))
        self.a.delete(event)
        self.assertEqual(self.a.pending_alerts(),[])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM agenda_exceptions').fetchone()[0],0)
        self.assertEqual(self.a.poll(self.ts('2026-10-18T08:50:00')),[])

    def test_invalid_input_is_rejected_without_partial_writes(self):
        invalid=[dict(title=' '),dict(end='2026-10-16T08:00:00'),dict(reminder_minutes=-1),
                 dict(reminder_minutes=True),dict(details='x'*4001),dict(color='url(evil)'),
                 dict(recurrence={'frequency':'weekly','weekdays':[]}),
                 dict(recurrence={'frequency':'daily','count':0}),
                 dict(recurrence={'frequency':'daily','until':'2026-01-01'}),
                 dict(recurrence={'frequency':'daily','count':2,'until':'2027-01-01'}),
                 dict(start='2026-10-16T09:00:00+02:00'),dict(timezone='invalid')]
        for fields in invalid:
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):self.event(**fields)
        for clock in ('8:00','25:00','12:60','nan','00:00:30'):
            with self.assertRaises(ValueError):self.a.save_alarm('Test',clock,now=self.now)
        with self.assertRaises(ValueError):self.a.save_alarm('Test','08:00',weekdays=[7],now=self.now)
        with self.assertRaises(ValueError):self.a.save_alarm('Test','08:00',now=float('nan'))
        self.assertEqual(self.a.events(),[]);self.assertEqual(self.a.alarms(self.now),[])

    def test_range_and_result_bounds_and_idle_poll_avoids_writes(self):
        self.event(recurrence={'frequency':'daily'})
        with self.assertRaises(ValueError):self.a.occurrences('2020-01-01','2030-01-01')
        with patch.object(agenda,'MAX_OCCURRENCES',2):
            with self.assertRaises(ValueError):self.a.occurrences('2026-10-01','2026-11-01')
        self.a.poll(self.now)
        statements=[];self.store.db.set_trace_callback(statements.append)
        self.a.poll(self.now+.1)
        self.store.db.set_trace_callback(None)
        self.assertEqual(statements,[])
        indexes={r[1] for r in self.store.db.execute('PRAGMA index_list(agenda_alerts)')}
        self.assertIn('agenda_alert_due',indexes)

    def test_old_frequent_rules_seek_directly_and_exhausted_count_has_no_future(self):
        rule={'frequency':'daily','interval':1}
        dates=list(agenda.recurrence_dates(date(1900,1,1),rule,date(2099,12,1),date(2100,1,1)))
        self.assertEqual(len(dates),31)
        event=self.event(start='1900-01-01T09:00:00',recurrence={'frequency':'daily','count':10000})
        self.assertIsNone(self.a.next_occurrence(event,self.now))
        self.assertIsNone(self.a.next_deadline(self.now))


if __name__=='__main__':unittest.main(verbosity=2)

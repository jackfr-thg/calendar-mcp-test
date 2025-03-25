-- SQL script to populate the calendar database with users, meeting rooms, and meetings

BEGIN TRANSACTION;

-- Add users
INSERT INTO users (name, email) VALUES ('Huzayfah', 'huzayfah@example.com');
INSERT INTO users (name, email) VALUES ('Jose', 'jose@example.com');
INSERT INTO users (name, email) VALUES ('Nier', 'nier@example.com');
INSERT INTO users (name, email) VALUES ('Yibo', 'yibo@example.com');
INSERT INTO users (name, email) VALUES ('Annie', 'annie@example.com');
INSERT INTO users (name, email) VALUES ('Anca', 'anca@example.com');
INSERT INTO users (name, email) VALUES ('Sarah', 'sarah@example.com');
INSERT INTO users (name, email) VALUES ('Robert', 'robert@example.com');
INSERT INTO users (name, email) VALUES ('Scott', 'scott@example.com');
INSERT INTO users (name, email) VALUES ('Mustafa', 'mustafa@example.com');
INSERT INTO users (name, email) VALUES ('Tadiwanashe', 'tadiwanashe@example.com');
INSERT INTO users (name, email) VALUES ('David', 'david@example.com');
INSERT INTO users (name, email) VALUES ('Edward', 'edward@example.com');
INSERT INTO users (name, email) VALUES ('Shaan', 'shaan@example.com');
INSERT INTO users (name, email) VALUES ('Henrietta', 'henrietta@example.com');
INSERT INTO users (name, email) VALUES ('Yu-Yang', 'yu-yang@example.com');
INSERT INTO users (name, email) VALUES ('Hugo', 'hugo@example.com');
INSERT INTO users (name, email) VALUES ('Yuhan', 'yuhan@example.com');
INSERT INTO users (name, email) VALUES ('Ozcan', 'ozcan@example.com');
INSERT INTO users (name, email) VALUES ('JackF', 'jackf@example.com');
INSERT INTO users (name, email) VALUES ('Hernan', 'hernan@example.com');
INSERT INTO users (name, email) VALUES ('JackL', 'jackl@example.com');

-- Add meeting rooms (room ID 1 might already exist as the virtual room, so we'll start from 2)
INSERT OR IGNORE INTO meeting_rooms (id, name, capacity, is_virtual) VALUES (1, 'Online Meeting', 999, 1);
INSERT INTO meeting_rooms (name, capacity, is_virtual) VALUES ('Meeting Room 1', 8, 0);
INSERT INTO meeting_rooms (name, capacity, is_virtual) VALUES ('Meeting Room 2', 12, 0);
INSERT INTO meeting_rooms (name, capacity, is_virtual) VALUES ('Meeting Room 3', 4, 0);
INSERT INTO meeting_rooms (name, capacity, is_virtual) VALUES ('Meeting Room 4', 20, 0);
INSERT INTO meeting_rooms (name, capacity, is_virtual) VALUES ('Meeting Room 5', 6, 0);

-- Add some random meetings (using dates relative to current date)
-- Meeting 1: Team Standup (happening today)
INSERT INTO events (title, description, start_time, end_time, meeting_room_id)
VALUES ('Team Standup', 'Daily team check-in', datetime('now', 'start of day', '+9 hours'), datetime('now', 'start of day', '+9 hours', '+30 minutes'), 3);

-- Get the ID of the last inserted event
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (2, last_insert_rowid(), 1); -- Jose as organizer
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (1, last_insert_rowid(), 0); -- Huzayfah
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (4, last_insert_rowid(), 0); -- Yibo
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (10, last_insert_rowid(), 0); -- Mustafa

-- Meeting 2: Project Planning (tomorrow)
INSERT INTO events (title, description, start_time, end_time, meeting_room_id)
VALUES ('Project Planning', 'Quarterly project planning session', datetime('now', '+1 day', 'start of day', '+13 hours'), datetime('now', '+1 day', 'start of day', '+15 hours'), 4);

INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (7, last_insert_rowid(), 1); -- Sarah as organizer
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (8, last_insert_rowid(), 0); -- Robert
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (9, last_insert_rowid(), 0); -- Scott
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (12, last_insert_rowid(), 0); -- David
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (15, last_insert_rowid(), 0); -- Henrietta
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (21, last_insert_rowid(), 0); -- Hernan

-- Meeting 3: Code Review (virtual meeting, in 2 days)
INSERT INTO events (title, description, start_time, end_time, meeting_room_id)
VALUES ('Code Review', 'Review PR #234 for the API refactoring', datetime('now', '+2 days', 'start of day', '+10 hours'), datetime('now', '+2 days', 'start of day', '+11 hours'), 1);

INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (3, last_insert_rowid(), 1); -- Nier as organizer
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (13, last_insert_rowid(), 0); -- Edward
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (18, last_insert_rowid(), 0); -- Yuhan

-- Meeting 4: Sprint Retrospective (in 3 days)
INSERT INTO events (title, description, start_time, end_time, meeting_room_id)
VALUES ('Sprint Retrospective', 'End of sprint review and planning', datetime('now', '+3 days', 'start of day', '+14 hours'), datetime('now', '+3 days', 'start of day', '+15 hours', '+30 minutes'), 2);

INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (20, last_insert_rowid(), 1); -- JackF as organizer
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (5, last_insert_rowid(), 0); -- Annie
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (6, last_insert_rowid(), 0); -- Anca
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (11, last_insert_rowid(), 0); -- Tadiwanashe
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (14, last_insert_rowid(), 0); -- Shaan
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (16, last_insert_rowid(), 0); -- Yu-Yang
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (17, last_insert_rowid(), 0); -- Hugo

-- Meeting 5: One-on-One (in 1 week)
INSERT INTO events (title, description, start_time, end_time, meeting_room_id)
VALUES ('One-on-One Meeting', 'Weekly check-in', datetime('now', '+7 days', 'start of day', '+11 hours'), datetime('now', '+7 days', 'start of day', '+12 hours'), 5);

INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (19, last_insert_rowid(), 1); -- Ozcan as organizer
INSERT INTO user_events (user_id, event_id, is_organizer)
VALUES (22, last_insert_rowid(), 0); -- JackL

COMMIT;

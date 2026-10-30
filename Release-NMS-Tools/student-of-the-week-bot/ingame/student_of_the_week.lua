-- Student of the Week: optional in-game message (UNTESTED, see README step 12).
--
-- Reads the bot's winner.txt and tells the player at login. Use it only if the bot runs
-- on the same machine as the zone servers, or if winner.txt is copied/synced to the path
-- below. Needs no client change.
--
-- Install: save as quests/global/student_of_the_week.lua, then add to the existing
-- quests/global/global_player.lua (create the file if the server has none):
--
--     local sotw = require('student_of_the_week')
--     function event_connect(e)
--         sotw.announce(e.self)
--     end
--
-- If global_player.lua already has an event_connect, call sotw.announce(e.self) from inside it.

local M = {}

-- Absolute path to the bot's data/winner.txt (use forward slashes, also on Windows).
M.WINNER_FILE = 'C:/student-of-the-week-bot/data/winner.txt'

-- Message colour (15 = yellow).
M.COLOR = 15

local function read_winner()
    local f = io.open(M.WINNER_FILE, 'r')
    if not f then
        return nil
    end
    local line = f:read('*l')
    f:close()
    if not line or line == '' then
        return nil
    end
    return line
end

function M.announce(client)
    local winner = read_winner()
    if winner then
        client:Message(M.COLOR, 'Student of the Week: ' .. winner .. '. Type /student in Discord for the link.')
    end
end

return M

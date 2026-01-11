using StravaSharp;
using StravaInfographics;

Authenticator authenticator = new(string.Empty);

Client client = new(authenticator);

Task<IEnumerable<ActivitySummary>> activities = client.Activities.GetAthleteActivities();


using StravaInfographics;
using Microsoft.Extensions.Configuration;
using Dumpify;

IConfiguration configuration = new ConfigurationBuilder()
    .AddUserSecrets<Program>()
    .Build();

Client client = await configuration.GetStravaClientAsync();

IEnumerable<ActivitySummary> activities = await client.Activities.GetAthleteActivities();

activities.Dump();

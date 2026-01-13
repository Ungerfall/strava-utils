using StravaSharp;
using StravaInfographics;
using Microsoft.Extensions.Configuration;
using Dumpify;

IConfigurationRoot configurationRoot = new ConfigurationBuilder()
    .AddUserSecrets<Program>()
    .Build();

string accessToken = configurationRoot["Strava:AccessToken"] ?? throw new ArgumentNullException(nameof(configurationRoot));
Authenticator authenticator = new(accessToken);
Client client = Client.Create(authenticator);

IEnumerable<ActivitySummary> activities = await client.Activities.GetAthleteActivities();

activities.Dump();


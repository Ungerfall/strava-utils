using StravaSharp;
using StravaSharp.OAuth2Client;
using StravaInfographics;
using Microsoft.Extensions.Configuration;
using Dumpify;

IConfigurationRoot configurationRoot = new ConfigurationBuilder()
    .AddUserSecrets<Program>()
    .Build();

OAuth2ClientConfiguration config = configurationRoot
    .GetSection("Strava")
    .GetAndValidate<OAuth2ClientConfiguration>();

StravaClient strava = new(config);

string accessToken = configurationRoot["Strava:AccessToken"] ?? throw new ArgumentNullException(nameof(configurationRoot));
Authenticator authenticator = new(accessToken);
Client client = Client.Create(authenticator);

IEnumerable<ActivitySummary> activities = await client.Activities.GetAthleteActivities();

activities.Dump();

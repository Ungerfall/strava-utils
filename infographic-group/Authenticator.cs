namespace StravaInfographics;

internal class Authenticator(string accessToken) : RestSharp.Authenticators.JwtAuthenticator(accessToken);

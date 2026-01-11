using RestSharp;

namespace StravaInfographics;

internal class Authenticator(string accessToken) : RestSharp.Authenticators.AuthenticatorBase(accessToken)
{
    protected override ValueTask<Parameter> GetAuthenticationParameter(string accessToken)
    {
        return new(new HeaderParameter("Authorization", "Bearer " + Token));
    }
}

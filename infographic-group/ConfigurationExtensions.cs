using Microsoft.Extensions.Configuration;
using System.ComponentModel.DataAnnotations;

namespace StravaInfographics;

public static class ConfigurationExtensions
{
    extension(IConfigurationSection section)
    {
        public T GetAndValidate<T>() where T : class
        {
            T? instance = section.Get<T>();
            if (instance == null)
                throw new ArgumentNullException(nameof(section), $"Configuration section '{section.Path}' could not be bound to {typeof(T).Name}.");

            ValidationContext validationContext = new(instance);
            Validator.ValidateObject(instance, validationContext, validateAllProperties: true);

            return instance;
        }
    }
}
